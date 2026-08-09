import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from payments.models import MpesaTransaction
from users.models import User

from .inventory import OrderInventoryService
from .models import Order
from .transitions import OrderTransitionService


logger = logging.getLogger(__name__)


class CustomerOrderCancellationService:
    """Cancel an unpaid online order through its protected customer access path."""

    REASON_PREFIX = 'Customer cancellation:'
    SAFE_MPESA_STATUSES = {
        MpesaTransaction.Status.INITIATING,
        MpesaTransaction.Status.PENDING,
        MpesaTransaction.Status.INITIATION_FAILED,
        MpesaTransaction.Status.FAILED,
    }

    @classmethod
    def deadline(cls, order):
        return order.created_at + timedelta(
            minutes=settings.CUSTOMER_ORDER_CANCELLATION_MINUTES,
        )

    @classmethod
    def eligibility(cls, order, *, now=None):
        now = now or timezone.now()
        if order.order_type == Order.OrderType.WALK_IN:
            return False, 'Walk-in sales use the staff return or void process.'
        if order.status == Order.Status.CANCELLED:
            return False, 'This order is already cancelled.'
        if now > cls.deadline(order):
            return False, 'The self-cancellation window has ended. Contact us on WhatsApp for help.'

        if order.payment_method == Order.PaymentMethod.COD:
            if order.status != Order.Status.PROCESSING:
                return False, 'This order has already moved into fulfilment.'
            return True, ''

        if order.payment_method == Order.PaymentMethod.MPESA_STK:
            if order.status != Order.Status.PENDING:
                return False, 'Payment or fulfilment has already progressed. Contact us for help.'
            try:
                payment = order.mpesa_payment
            except MpesaTransaction.DoesNotExist:
                payment = None
            if payment is not None and payment.status not in cls.SAFE_MPESA_STATUSES:
                return False, 'M-Pesa evidence is being checked. Contact us before cancelling.'
            return True, ''

        return False, 'This payment method requires staff assistance to cancel.'

    @classmethod
    @transaction.atomic
    def cancel(cls, *, order, requested_by=None):
        locked = Order.objects.select_for_update(of=('self',)).select_related(
            'customer', 'processed_by', 'branch',
        ).get(pk=order.pk)
        allowed, message = cls.eligibility(locked)
        if not allowed:
            raise ValidationError(message, code='cancellation_unavailable')

        actor = requested_by or locked.customer or locked.processed_by or User.get_system_account()
        reason = (
            f'{cls.REASON_PREFIX} cancelled through the protected tracking page within '
            f'{settings.CUSTOMER_ORDER_CANCELLATION_MINUTES} minutes of placement.'
        )
        OrderInventoryService.release_reservations(
            order=locked,
            actor=actor,
            note='Reservation released after customer self-cancellation.',
        )
        cancelled = OrderTransitionService.transition(
            order=locked,
            to_status=Order.Status.CANCELLED,
            changed_by=actor,
            note='Customer cancelled the order through the protected tracking page.',
            extra_updates={'void_reason': reason},
        )

        order_id = str(cancelled.pk)

        def queue_confirmation():
            try:
                from notifications.tasks import send_customer_cancelled_order_sms
                send_customer_cancelled_order_sms.delay(order_id)
            except Exception as exc:
                logger.error(
                    'Customer cancellation committed but notification could not be queued | '
                    'OrderID=%s | ExceptionType=%s',
                    cancelled.pk,
                    type(exc).__name__,
                )

        transaction.on_commit(queue_confirmation)
        return cancelled
