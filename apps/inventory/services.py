from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Stock, StockAuditLog


class InventoryService:
    """Atomic controller for every inventory-state mutation."""

    @staticmethod
    def _lookup(*, branch, variant=None, product=None):
        if bool(variant) == bool(product):
            raise ValueError("Provide exactly one of 'variant' or 'product'.")
        return {
            'branch': branch,
            'variant': variant if variant else None,
            'product': product if product else None,
        }

    @classmethod
    def _locked_stock(cls, **kwargs):
        lookup = cls._lookup(**kwargs)
        stock, _ = Stock.objects.select_for_update().get_or_create(
            **lookup,
            defaults={
                'quantity': 0,
                'reserved_quantity': 0,
                'in_transit_quantity': 0,
                'damaged_quantity': 0,
            },
        )
        return stock

    @classmethod
    def _lock_transfer_stocks(cls, *, from_branch, to_branch, variant=None, product=None):
        """Lock both transfer balances in one deterministic branch order."""
        if from_branch.pk == to_branch.pk:
            raise ValidationError("Source and destination branches must be different.")

        locked_by_branch_id = {}
        for branch in sorted((from_branch, to_branch), key=lambda item: item.pk):
            locked_by_branch_id[branch.pk] = cls._locked_stock(
                branch=branch, variant=variant, product=product,
            )
        return locked_by_branch_id[from_branch.pk], locked_by_branch_id[to_branch.pk]

    @staticmethod
    def _audit(*, stock, reason, triggered_by, change_amount=0,
               reference_number=None, note=''):
        return StockAuditLog.objects.create(
            variant=stock.variant,
            product=stock.product,
            branch=stock.branch,
            change_amount=change_amount,
            running_total=stock.quantity,
            reserved_total=stock.reserved_quantity,
            in_transit_total=stock.in_transit_quantity,
            damaged_total=stock.damaged_quantity,
            reason=reason,
            note=note,
            reference_number=reference_number,
            triggered_by=triggered_by,
        )

    @staticmethod
    def _existing_movement(*, stock, reason, reference_number):
        if not reference_number:
            return None
        return StockAuditLog.objects.filter(
            branch=stock.branch,
            variant=stock.variant,
            product=stock.product,
            reason=reason,
            reference_number=reference_number,
        ).first()

    @classmethod
    @transaction.atomic
    def adjust_stock(cls, branch, change_amount, reason, triggered_by,
                     variant=None, product=None, reference_number=None, note=''):
        """Change sellable on-hand stock without consuming reserved units."""
        manual_reasons = {
            StockAuditLog.Reason.CORRECTION,
            StockAuditLog.Reason.DAMAGE,
            StockAuditLog.Reason.THEFT,
        }
        if reason in manual_reasons and not note:
            raise ValidationError(f"A note is required for '{reason}' adjustments.")
        stock = cls._locked_stock(
            branch=branch, variant=variant, product=product,
        )
        new_quantity = stock.quantity + int(change_amount)
        if new_quantity < stock.reserved_quantity:
            raise ValidationError(
                f"Inventory change blocked: {stock.available_quantity} available unit(s); "
                f"{stock.reserved_quantity} are reserved."
            )
        stock.quantity = new_quantity
        stock.save(update_fields=['quantity'])
        audit = cls._audit(
            stock=stock, reason=reason, triggered_by=triggered_by,
            change_amount=int(change_amount), reference_number=reference_number,
            note=note,
        )
        return stock, audit

    @classmethod
    @transaction.atomic
    def reserve_stock(cls, *, branch, quantity, triggered_by, reference_number,
                      variant=None, product=None, note=''):
        quantity = int(quantity)
        if quantity <= 0 or not reference_number:
            raise ValidationError("A positive quantity and reservation reference are required.")
        stock = cls._locked_stock(branch=branch, variant=variant, product=product)
        existing = cls._existing_movement(
            stock=stock, reason=StockAuditLog.Reason.RESERVATION,
            reference_number=reference_number,
        )
        if existing:
            return stock, existing, False
        if stock.available_quantity < quantity:
            raise ValidationError(
                f"Reservation blocked: only {stock.available_quantity} available unit(s)."
            )
        stock.reserved_quantity += quantity
        stock.save(update_fields=['reserved_quantity'])
        audit = cls._audit(
            stock=stock, reason=StockAuditLog.Reason.RESERVATION,
            triggered_by=triggered_by, reference_number=reference_number,
            note=note,
        )
        return stock, audit, True

    @classmethod
    @transaction.atomic
    def release_reservation(cls, *, branch, quantity, triggered_by, reference_number,
                            variant=None, product=None, note=''):
        quantity = int(quantity)
        stock = cls._locked_stock(branch=branch, variant=variant, product=product)
        existing = cls._existing_movement(
            stock=stock, reason=StockAuditLog.Reason.RESERVATION_RELEASE,
            reference_number=reference_number,
        )
        if existing:
            return stock, existing, False
        if quantity <= 0 or stock.reserved_quantity < quantity:
            raise ValidationError("Reservation release exceeds the reserved balance.")
        stock.reserved_quantity -= quantity
        stock.save(update_fields=['reserved_quantity'])
        audit = cls._audit(
            stock=stock, reason=StockAuditLog.Reason.RESERVATION_RELEASE,
            triggered_by=triggered_by, reference_number=reference_number,
            note=note,
        )
        return stock, audit, True

    @classmethod
    @transaction.atomic
    def consume_reservation(cls, *, branch, quantity, triggered_by, reference_number,
                            variant=None, product=None, note=''):
        quantity = int(quantity)
        stock = cls._locked_stock(branch=branch, variant=variant, product=product)
        existing = cls._existing_movement(
            stock=stock, reason=StockAuditLog.Reason.RESERVATION_CONSUMED,
            reference_number=reference_number,
        )
        if existing:
            return stock, existing, False
        if quantity <= 0 or stock.reserved_quantity < quantity or stock.quantity < quantity:
            raise ValidationError("Reservation consumption exceeds the committed balance.")
        stock.reserved_quantity -= quantity
        stock.quantity -= quantity
        stock.save(update_fields=['reserved_quantity', 'quantity'])
        audit = cls._audit(
            stock=stock, reason=StockAuditLog.Reason.RESERVATION_CONSUMED,
            triggered_by=triggered_by, change_amount=-quantity,
            reference_number=reference_number, note=note,
        )
        return stock, audit, True

    @classmethod
    @transaction.atomic
    def quarantine_damaged_stock(cls, *, branch, quantity, triggered_by,
                                 variant=None, product=None,
                                 reference_number=None, note=''):
        quantity = int(quantity)
        if quantity <= 0 or not note:
            raise ValidationError("A positive quantity and quarantine note are required.")
        stock = cls._locked_stock(branch=branch, variant=variant, product=product)
        if stock.available_quantity < quantity:
            raise ValidationError("Damage quarantine exceeds available stock.")
        stock.quantity -= quantity
        stock.damaged_quantity += quantity
        stock.save(update_fields=['quantity', 'damaged_quantity'])
        audit = cls._audit(
            stock=stock, reason=StockAuditLog.Reason.DAMAGE_QUARANTINE,
            triggered_by=triggered_by, change_amount=-quantity,
            reference_number=reference_number, note=note,
        )
        return stock, audit

    @classmethod
    @transaction.atomic
    def dispatch_transfer(cls, *, branch, quantity, triggered_by, reference_number,
                          variant=None, product=None, note=''):
        quantity = int(quantity)
        stock = cls._locked_stock(branch=branch, variant=variant, product=product)
        existing = cls._existing_movement(
            stock=stock, reason=StockAuditLog.Reason.TRANSFER_OUT,
            reference_number=reference_number,
        )
        if existing:
            return stock, existing, False
        if quantity <= 0 or stock.available_quantity < quantity:
            raise ValidationError("Transfer dispatch exceeds available stock.")
        stock.quantity -= quantity
        stock.in_transit_quantity += quantity
        stock.save(update_fields=['quantity', 'in_transit_quantity'])
        audit = cls._audit(
            stock=stock, reason=StockAuditLog.Reason.TRANSFER_OUT,
            triggered_by=triggered_by, change_amount=-quantity,
            reference_number=reference_number, note=note,
        )
        return stock, audit, True

    @classmethod
    @transaction.atomic
    def receive_transfer(cls, *, from_branch, to_branch, quantity, triggered_by,
                         reference_number, variant=None, product=None, note=''):
        quantity = int(quantity)
        source, destination = cls._lock_transfer_stocks(
            from_branch=from_branch, to_branch=to_branch,
            variant=variant, product=product,
        )
        existing = cls._existing_movement(
            stock=destination, reason=StockAuditLog.Reason.TRANSFER_IN,
            reference_number=reference_number,
        )
        if existing:
            return source, destination, existing, False
        if quantity <= 0 or source.in_transit_quantity < quantity:
            raise ValidationError("Transfer receipt exceeds the in-transit balance.")
        source.in_transit_quantity -= quantity
        destination.quantity += quantity
        source.save(update_fields=['in_transit_quantity'])
        destination.save(update_fields=['quantity'])
        audit = cls._audit(
            stock=destination, reason=StockAuditLog.Reason.TRANSFER_IN,
            triggered_by=triggered_by, change_amount=quantity,
            reference_number=reference_number, note=note,
        )
        return source, destination, audit, True

    @classmethod
    @transaction.atomic
    def quarantine_return(cls, *, branch, quantity, triggered_by, reference_number,
                          variant=None, product=None, note=''):
        stock = cls._locked_stock(branch=branch, variant=variant, product=product)
        if cls._existing_movement(
            stock=stock, reason=StockAuditLog.Reason.RETURN,
            reference_number=reference_number,
        ):
            return stock, None, False
        quantity = int(quantity)
        if quantity <= 0:
            raise ValidationError("Return quantity must be positive.")
        stock.damaged_quantity += quantity
        stock.save(update_fields=['damaged_quantity'])
        audit = cls._audit(
            stock=stock, reason=StockAuditLog.Reason.RETURN,
            triggered_by=triggered_by, reference_number=reference_number,
            note=note,
        )
        return stock, audit, True
