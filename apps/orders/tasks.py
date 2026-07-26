# apps/orders/tasks.py
# Hardened version -- fixes a batch-fragility bug in the version written
# last turn: each order is now processed in its own isolated try/except
# so one bad order (e.g. an unexpected InventoryService failure) can't
# kill the entire sweep and leave every OTHER abandoned order uncleaned
# until the next scheduled run 5 minutes later.

import logging
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from celery import shared_task

logger = logging.getLogger(__name__)

ABANDONED_ORDER_TIMEOUT_MINUTES = 30


@shared_task(name='orders.cancel_abandoned_pending_orders')
def cancel_abandoned_pending_orders():
    """
    Scheduled every 5 minutes via Celery Beat.

    Finds ONLINE orders stuck in PENDING (awaiting M-Pesa STK
    confirmation) for longer than ABANDONED_ORDER_TIMEOUT_MINUTES,
    cancels them, and reverses the stock they had deducted.

    COD orders are NEVER touched here -- they skip PENDING entirely
    and go straight to PROCESSING, so this query structurally excludes
    them with no special-case filter.

    Each order is processed in its own try/except -- a failure on one
    order is logged and the sweep continues to the next, rather than
    one bad order silently blocking cleanup of every other abandoned
    order until the next scheduled run.
    """
    from orders.models import Order, OrderItem
    from orders.transitions import OrderTransitionService
    from orders.inventory import OrderInventoryService
    from notifications.tasks import send_order_auto_cancelled_sms

    cutoff = timezone.now() - timedelta(minutes=ABANDONED_ORDER_TIMEOUT_MINUTES)

    candidate_ids = list(
        Order.objects.filter(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            created_at__lte=cutoff,
        ).values_list('id', flat=True)
    )

    if not candidate_ids:
        logger.info("Abandoned checkout sweep: nothing to cancel.")
        return

    cancelled_count = 0
    failed_count = 0

    for order_id in candidate_ids:
        try:
            _cancel_single_abandoned_order(order_id)
            cancelled_count += 1
        except Order.DoesNotExist:
            # Already confirmed/cancelled between the query above and
            # acquiring the lock -- not an error, skip silently.
            continue
        except Exception as exc:
            # Isolated per-order: this order's failure is logged, but
            # the sweep continues to every other candidate rather than
            # dying here and leaving the rest uncleaned for 5 more minutes.
            failed_count += 1
            logger.error(
                f"Abandoned checkout sweep: failed to cancel order "
                f"{order_id}: {exc}",
                exc_info=True,
            )
            continue

        try:
            send_order_auto_cancelled_sms.delay(str(order_id))
        except Exception as e:
            logger.error(
                f"Order {order_id} auto-cancelled successfully, but the "
                f"notification SMS could not be queued: {e}"
            )

    logger.info(
        f"Abandoned checkout sweep complete: {cancelled_count} cancelled, "
        f"{failed_count} failed, stock released for cancelled orders."
    )



def _cancel_single_abandoned_order(order_id):
    """
    Cancels one abandoned order and reverses its stock, fully atomic.
    Raises Order.DoesNotExist if it was already handled by something
    else between the candidate query and lock acquisition -- caller
    treats that as a normal skip, not an error.
    """
    from orders.models import Order, OrderItem
    from orders.transitions import OrderTransitionService
    from orders.inventory import OrderInventoryService
    from users.models import User
    with transaction.atomic():
        # Lock the order row and re-check status INSIDE the lock -- a
        # payment callback may have confirmed it moments ago.
        order = Order.objects.select_for_update().get(
            id=order_id,
            status=Order.Status.PENDING,
        )

        void_reason = (
            f"Auto-cancelled: no payment confirmation received within "
            f"{ABANDONED_ORDER_TIMEOUT_MINUTES} minutes."
        )
        # triggered_by/changed_by: order.customer is None for guest
        # checkouts (phone-only per §1) -- both FKs below are required
        # (non-null), so a real actor must always be supplied. Falls back
        # to the system automation account rather than crashing mid-atomic.
        actor = order.customer or User.get_system_account()
        OrderInventoryService.release_reservations(
            order=order,
            actor=actor,
            note=(
                f"Reservation released after {ABANDONED_ORDER_TIMEOUT_MINUTES} "
                f"minutes unpaid."
            ),
        )
        OrderTransitionService.transition(
            order=order,
            to_status=Order.Status.CANCELLED,
            note=(
                f"Auto-cancelled by system: payment not received "
                f"within {ABANDONED_ORDER_TIMEOUT_MINUTES} minutes."
            ),
            changed_by=actor,
            extra_updates={'void_reason': void_reason},
        )

PICKUP_REMINDER_HOURS = 24
@shared_task(name='orders.send_pickup_reminders')
def send_pickup_reminders():
    """
    Scheduled hourly. Sends a one-time reminder SMS for orders that have
    sat in READY_FOR_PICKUP for >= PICKUP_REMINDER_HOURS. "Ready since"
    is derived from OrderStatusHistory rather than a dedicated timestamp
    field on Order, since whatever view transitions the order to
    READY_FOR_PICKUP already writes that history entry (established
    pattern across this codebase).
    """
    from orders.models import Order, OrderStatusHistory
    from notifications.tasks import send_pickup_reminder_sms
    cutoff = timezone.now() - timedelta(hours=PICKUP_REMINDER_HOURS)
    candidates = Order.objects.filter(
        status=Order.Status.READY_FOR_PICKUP,
        pickup_reminder_sent_at__isnull=True,
    )
    sent = 0
    for order in candidates:
        ready_entry = OrderStatusHistory.objects.filter(
            order=order, new_status=Order.Status.READY_FOR_PICKUP,
        ).order_by('-created_at').first()
        if not ready_entry or ready_entry.created_at > cutoff:
            continue
        Order.objects.filter(id=order.id).update(pickup_reminder_sent_at=timezone.now())
        try:
            send_pickup_reminder_sms.delay(str(order.id))
            sent += 1
        except Exception as exc:
            logger.error(
                "Order reminder flagged sent, but SMS could not be queued | "
                "OrderID=%s | ExceptionType=%s",
                order.id,
                type(exc).__name__,
            )
    logger.info(f"Pickup reminder sweep: {sent} reminder(s) sent.")
@shared_task(name='orders.auto_cancel_unresolved_pickups')
def auto_cancel_unresolved_pickups():
    """
    Scheduled hourly. Cancels and restores stock only after the persisted
    two-working-day pickup deadline. Mirrors
    cancel_abandoned_pending_orders's per-order isolation: one bad order
    is logged and skipped, never blocks the rest of the sweep.
    """
    from orders.models import Order
    candidate_ids = list(
        Order.objects.filter(status=Order.Status.READY_FOR_PICKUP).values_list('id', flat=True)
    )
    if not candidate_ids:
        logger.info("Unresolved pickup sweep: nothing to cancel.")
        return
    now = timezone.now()
    cancelled_count = 0
    failed_count = 0
    for order_id in candidate_ids:
        try:
            if _cancel_single_unresolved_pickup(order_id, now):
                cancelled_count += 1
        except Order.DoesNotExist:
            continue
        except Exception as exc:
            failed_count += 1
            logger.error(
                "Unresolved pickup sweep failed | OrderID=%s | ExceptionType=%s",
                order_id,
                type(exc).__name__,
            )
            continue
    logger.info(
        f"Unresolved pickup sweep complete: {cancelled_count} cancelled, "
        f"{failed_count} failed."
    )
def _cancel_single_unresolved_pickup(order_id, now):
    from orders.models import Order
    from orders.transitions import OrderTransitionService
    from orders.inventory import OrderInventoryService
    from users.models import User
    from notifications.tasks import send_order_auto_cancelled_sms, send_pickup_auto_cancel_manager_alert
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id, status=Order.Status.READY_FOR_PICKUP)
        if order.pickup_expires_at is None or order.pickup_expires_at > now:
            return False
        void_reason = 'Auto-cancelled: uncollected pickup passed its two-working-day deadline.'
        actor = order.customer or User.get_system_account()
        OrderInventoryService.release_reservations(
            order=order,
            actor=actor,
            note='Reservation released after the pickup collection deadline passed.',
        )
        OrderTransitionService.transition(
            order=order, to_status=Order.Status.CANCELLED,
            note='Auto-cancelled: not collected within two working days.',
            changed_by=actor,
            extra_updates={'void_reason': void_reason},
        )
        order_id_str = str(order.id)
        transaction.on_commit(lambda: send_order_auto_cancelled_sms.delay(order_id_str))
        transaction.on_commit(lambda: send_pickup_auto_cancel_manager_alert.delay(order_id_str))
    return True
