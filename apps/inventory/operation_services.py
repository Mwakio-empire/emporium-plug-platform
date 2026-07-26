from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Stock, StockAuditLog, StockCount, StockCountLine
from .services import InventoryService


class InventoryOperationsService:
    ALLOWED_ROLES = ('INVENTORY_MANAGER', 'BRANCH_MANAGER', 'SUPER_ADMIN')

    @classmethod
    def _assert_actor(cls, actor, branch):
        if actor.role not in cls.ALLOWED_ROLES:
            raise ValidationError("You are not authorized to manage inventory.")
        if actor.role != 'SUPER_ADMIN' and actor.branch_id != branch.pk:
            raise ValidationError("You can only manage inventory at your assigned branch.")

    @classmethod
    @transaction.atomic
    def record_manual_adjustment(cls, *, branch, actor, change_amount, reason,
                                 reference_number, note, product=None, variant=None):
        cls._assert_actor(actor, branch)
        if reason not in {
            StockAuditLog.Reason.CORRECTION,
            StockAuditLog.Reason.DAMAGE,
            StockAuditLog.Reason.THEFT,
        }:
            raise ValidationError("Unsupported manual adjustment reason.")
        reference_number = reference_number.strip() if reference_number else ''
        note = note.strip() if note else ''
        change_amount = int(change_amount)
        if not reference_number or not note or change_amount == 0:
            raise ValidationError("A reference, note and non-zero stock change are required.")
        if reason in {StockAuditLog.Reason.DAMAGE, StockAuditLog.Reason.THEFT} and change_amount >= 0:
            raise ValidationError("Damage and theft adjustments must reduce sellable stock.")

        stock = InventoryService._locked_stock(
            branch=branch, product=product, variant=variant,
        )
        audit_reason = (
            StockAuditLog.Reason.DAMAGE_QUARANTINE
            if reason == StockAuditLog.Reason.DAMAGE else reason
        )
        existing = InventoryService._existing_movement(
            stock=stock, reason=audit_reason, reference_number=reference_number,
        )
        if existing:
            return stock, existing, False

        if reason == StockAuditLog.Reason.DAMAGE:
            stock, audit = InventoryService.quarantine_damaged_stock(
                branch=branch, product=product, variant=variant,
                quantity=abs(change_amount), triggered_by=actor,
                reference_number=reference_number, note=note,
            )
        else:
            stock, audit = InventoryService.adjust_stock(
                branch=branch, product=product, variant=variant,
                change_amount=change_amount, reason=reason,
                triggered_by=actor, reference_number=reference_number, note=note,
            )
        return stock, audit, True

    @classmethod
    @transaction.atomic
    def start_count(cls, *, branch, actor, stock_ids=None, notes=''):
        cls._assert_actor(actor, branch)
        if not branch.is_active:
            raise ValidationError("A stock count cannot start at an inactive branch.")
        if StockCount.objects.select_for_update().filter(
            branch=branch, status=StockCount.Status.OPEN,
        ).exists():
            raise ValidationError("This branch already has an open stock count.")
        stocks = Stock.objects.select_for_update().filter(branch=branch).order_by('pk')
        if stock_ids:
            stocks = stocks.filter(pk__in=stock_ids)
        stocks = list(stocks)
        if not stocks:
            raise ValidationError("No branch stock records were selected for counting.")
        count = StockCount.objects.create(
            branch=branch, started_by=actor, notes=notes.strip(),
        )
        StockCountLine.objects.bulk_create([
            StockCountLine(
                stock_count=count, product=stock.product, variant=stock.variant,
                expected_quantity=stock.quantity,
            )
            for stock in stocks
        ])
        return count

    @classmethod
    @transaction.atomic
    def record_counted_quantity(cls, *, stock_count_id, line_id, actor, quantity):
        count = StockCount.objects.select_for_update().get(pk=stock_count_id)
        cls._assert_actor(actor, count.branch)
        if count.status != StockCount.Status.OPEN:
            raise ValidationError("Only an open stock count can be updated.")
        quantity = int(quantity)
        if quantity < 0:
            raise ValidationError("Counted quantity cannot be negative.")
        line = StockCountLine.objects.select_for_update().get(
            pk=line_id, stock_count=count,
        )
        line.counted_quantity = quantity
        line.save(update_fields=['counted_quantity'])
        return line

    @classmethod
    @transaction.atomic
    def complete_count(cls, *, stock_count_id, actor):
        count = StockCount.objects.select_for_update().select_related('branch').get(
            pk=stock_count_id,
        )
        cls._assert_actor(actor, count.branch)
        if count.status != StockCount.Status.OPEN:
            raise ValidationError("Only an open stock count can be completed.")
        lines = list(count.lines.select_for_update().order_by('pk'))
        if any(line.counted_quantity is None for line in lines):
            raise ValidationError("Every stock-count line must be counted before completion.")

        for line in lines:
            movement = StockAuditLog.objects.filter(
                branch=count.branch,
                product=line.product,
                variant=line.variant,
                timestamp__gt=count.started_at,
            ).exists()
            if movement:
                raise ValidationError(
                    "Stock moved after this count began. Cancel it and start a fresh count."
                )

        for line in lines:
            change = line.counted_quantity - line.expected_quantity
            if change:
                InventoryService.adjust_stock(
                    branch=count.branch, product=line.product, variant=line.variant,
                    change_amount=change, reason=StockAuditLog.Reason.CORRECTION,
                    triggered_by=actor,
                    reference_number=f"COUNT-{count.pk}-LINE-{line.pk}",
                    note=(
                        f"Stock count correction: expected {line.expected_quantity}, "
                        f"counted {line.counted_quantity}."
                    ),
                )
        count.status = StockCount.Status.COMPLETED
        count.completed_by = actor
        count.completed_at = timezone.now()
        count.save(update_fields=['status', 'completed_by', 'completed_at'])
        return count

    @classmethod
    @transaction.atomic
    def cancel_count(cls, *, stock_count_id, actor, reason):
        count = StockCount.objects.select_for_update().get(pk=stock_count_id)
        cls._assert_actor(actor, count.branch)
        if count.status != StockCount.Status.OPEN:
            raise ValidationError("Only an open stock count can be cancelled.")
        reason = reason.strip() if reason else ''
        if not reason:
            raise ValidationError("A cancellation reason is required.")
        count.status = StockCount.Status.CANCELLED
        count.cancelled_by = actor
        count.cancelled_at = timezone.now()
        count.cancellation_reason = reason
        count.save(update_fields=[
            'status', 'cancelled_by', 'cancelled_at', 'cancellation_reason',
        ])
        return count
