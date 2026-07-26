from django.core.exceptions import ValidationError
from django.db import transaction

from .models import StockAuditLog, StockIntake, StockIntakeLine
from .services import InventoryService


class SupplierIntakeService:
    """Books an external supplier delivery into a configured receiving hub."""

    ALLOWED_ROLES = ('INVENTORY_MANAGER', 'BRANCH_MANAGER', 'SUPER_ADMIN')

    @staticmethod
    def _line_key(line):
        product = line.get('product')
        variant = line.get('variant')
        return (
            f"p:{product.pk}" if product else f"v:{variant.pk}",
            int(line.get('quantity', 0)),
        )

    @classmethod
    @transaction.atomic
    def record_intake(cls, *, branch, supplier_name, delivery_reference,
                      received_by, lines, notes=''):
        supplier_name = supplier_name.strip() if supplier_name else ''
        delivery_reference = delivery_reference.strip() if delivery_reference else ''
        if not branch.is_active:
            raise ValidationError("Supplier stock cannot be received at an inactive branch.")
        if not branch.receives_supplier_stock:
            raise ValidationError("This branch is not configured to receive supplier stock.")
        if received_by.role not in cls.ALLOWED_ROLES:
            raise ValidationError("You are not authorized to record supplier stock intake.")
        if received_by.role != 'SUPER_ADMIN' and received_by.branch_id != branch.pk:
            raise ValidationError("You can only record intake for your assigned branch.")
        if not supplier_name or not delivery_reference:
            raise ValidationError("Supplier name and delivery reference are required.")
        if not lines:
            raise ValidationError("At least one intake line is required.")

        normalized = []
        seen = set()
        for line in lines:
            product = line.get('product')
            variant = line.get('variant')
            if bool(product) == bool(variant):
                raise ValidationError("Each intake line must contain one product or one variant.")
            quantity = int(line.get('quantity', 0))
            if quantity <= 0:
                raise ValidationError("Every intake quantity must be greater than zero.")
            if product and product.variants.exists():
                raise ValidationError(
                    f"{product.name} has variants; receive a specific variant instead."
                )
            key = f"p:{product.pk}" if product else f"v:{variant.pk}"
            if key in seen:
                raise ValidationError("Duplicate catalog items are not allowed in one intake.")
            seen.add(key)
            normalized.append({
                'product': product, 'variant': variant, 'quantity': quantity,
            })

        existing = StockIntake.objects.prefetch_related('lines').filter(
            branch=branch, delivery_reference=delivery_reference,
        ).first()
        if existing:
            existing_lines = sorted(
                (
                    f"p:{line.product_id}" if line.product_id else f"v:{line.variant_id}",
                    line.quantity,
                )
                for line in existing.lines.all()
            )
            requested_lines = sorted(cls._line_key(line) for line in normalized)
            if existing.supplier_name == supplier_name and existing_lines == requested_lines:
                return existing, False
            raise ValidationError(
                "This delivery reference already exists with different intake details."
            )

        intake = StockIntake.objects.create(
            branch=branch, supplier_name=supplier_name,
            delivery_reference=delivery_reference,
            received_by=received_by, notes=notes.strip(),
        )
        for line in normalized:
            intake_line = StockIntakeLine.objects.create(
                intake=intake, product=line['product'], variant=line['variant'],
                quantity=line['quantity'],
            )
            InventoryService.adjust_stock(
                branch=branch, product=line['product'], variant=line['variant'],
                change_amount=line['quantity'],
                reason=StockAuditLog.Reason.RESTOCK,
                triggered_by=received_by,
                reference_number=f"INTAKE-{intake.pk}-LINE-{intake_line.pk}",
                note=f"Supplier: {supplier_name}; delivery: {delivery_reference}.",
            )
        return intake, True
