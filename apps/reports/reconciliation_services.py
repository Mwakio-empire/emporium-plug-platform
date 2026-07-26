from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum, Q
from django.utils import timezone

from .models import OperationalAuditRiskLog, POSShift, ShiftReconciliation


CASH_VARIANCE_ALERT_THRESHOLD = Decimal('50.00')


def _money(value):
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Enter a valid monetary amount.') from None


class POSShiftService:
    @staticmethod
    def current_shift(cashier):
        return POSShift.objects.filter(
            cashier=cashier,
            branch=cashier.branch,
            status=POSShift.Status.OPEN,
        ).first()

    @staticmethod
    @transaction.atomic
    def open_shift(*, cashier, opening_cash=Decimal('0.00')):
        from users.models import User

        if cashier.role not in {
            User.Role.STAFF,
            User.Role.BRANCH_MANAGER,
            User.Role.SUPER_ADMIN,
        } or cashier.branch is None:
            raise ValidationError('Only branch-assigned POS staff may open a shift.')
        opening_cash = _money(opening_cash)
        if opening_cash < 0:
            raise ValidationError('Opening cash cannot be negative.')

        User.objects.select_for_update().get(pk=cashier.pk)
        existing = POSShift.objects.filter(
            cashier=cashier,
            status=POSShift.Status.OPEN,
        ).first()
        if existing:
            return existing, False
        try:
            with transaction.atomic():
                shift = POSShift.objects.create(
                    cashier=cashier,
                    branch=cashier.branch,
                    opening_cash=opening_cash,
                )
        except IntegrityError:
            shift = POSShift.objects.get(cashier=cashier, status=POSShift.Status.OPEN)
            return shift, False
        return shift, True


class ShiftReconciliationService:
    @staticmethod
    @transaction.atomic
    def close_shift(*, cashier, actual_cash, notes=''):
        if cashier.branch is None:
            raise ValidationError('Cashier is not assigned to a branch.')
        actual_cash = _money(actual_cash)
        if actual_cash < 0:
            raise ValidationError('Actual cash cannot be negative.')

        try:
            shift = POSShift.objects.select_for_update().get(
                cashier=cashier,
                branch=cashier.branch,
                status=POSShift.Status.OPEN,
            )
        except POSShift.DoesNotExist:
            raise ValidationError('No open POS shift exists for this cashier.') from None

        totals = shift.orders.filter(status='COMPLETED').aggregate(
            cash=Sum('total_payable', filter=Q(payment_method='CASH')),
            paybill=Sum('total_payable', filter=Q(payment_method='PAYBILL')),
            mpesa=Sum('total_payable', filter=Q(payment_method='MPESA_STK')),
        )
        expected_cash = shift.opening_cash + (totals['cash'] or Decimal('0.00'))
        mpesa_settled = (totals['paybill'] or Decimal('0.00')) + (
            totals['mpesa'] or Decimal('0.00')
        )
        variance = actual_cash - expected_cash
        requires_review = abs(variance) > CASH_VARIANCE_ALERT_THRESHOLD
        notes = str(notes or '').strip()
        reconciliation = ShiftReconciliation.objects.create(
            pos_shift=shift,
            branch=shift.branch,
            cashier=cashier,
            opened_at=shift.opened_at,
            expected_cash=expected_cash,
            actual_cash=actual_cash,
            mpesa_total_settled=mpesa_settled,
            notes=notes,
            requires_manager_review=requires_review,
        )
        shift.status = POSShift.Status.CLOSED
        shift.closed_at = timezone.now()
        shift.save(update_fields=['status', 'closed_at'])

        if requires_review:
            reconciliation_id = reconciliation.id
            transaction.on_commit(
                lambda: ShiftReconciliationService._notify_variance(reconciliation_id)
            )
        return reconciliation

    @staticmethod
    def _notify_variance(reconciliation_id):
        from notifications.tasks import send_shift_variance_alert
        send_shift_variance_alert.delay(reconciliation_id)

    @staticmethod
    @transaction.atomic
    def verify_reconciliation(*, reconciliation_id, manager, reason):
        from users.models import User

        if manager.role not in {User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN}:
            raise ValidationError('Only branch managers or super admins can verify reconciliations.')
        reason = str(reason or '').strip()
        if len(reason) < 10:
            raise ValidationError('A verification reason of at least 10 characters is required.')
        try:
            reconciliation = ShiftReconciliation.objects.select_for_update().get(
                id=reconciliation_id,
            )
        except ShiftReconciliation.DoesNotExist:
            raise ValidationError('Shift reconciliation not found.') from None
        if manager.role == User.Role.BRANCH_MANAGER and manager.branch_id != reconciliation.branch_id:
            raise ValidationError('You can only verify reconciliations for your own branch.')
        if not reconciliation.requires_manager_review:
            raise ValidationError('This reconciliation does not require manager review.')
        if reconciliation.is_verified_by_manager:
            raise ValidationError('This reconciliation has already been verified.')

        reconciliation.is_verified_by_manager = True
        reconciliation.verified_by = manager
        reconciliation.verified_at = timezone.now()
        reconciliation.verification_reason = reason
        reconciliation.save(update_fields=[
            'is_verified_by_manager', 'verified_by', 'verified_at', 'verification_reason',
        ])
        OperationalAuditRiskLog.objects.create(
            branch=reconciliation.branch,
            initiator=manager,
            action_type='SHIFT_VARIANCE_VERIFIED',
            severity=OperationalAuditRiskLog.RiskSeverity.HIGH,
            target_record_id=str(reconciliation.pk),
            justification_trail=reason,
            metadata_payload={
                'cashier_id': reconciliation.cashier_id,
                'variance': str(reconciliation.cash_variance),
                'shift_id': reconciliation.pos_shift_id,
            },
        )
        return reconciliation
