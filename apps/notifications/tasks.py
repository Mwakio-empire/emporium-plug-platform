# apps/notifications/tasks.py
# Full hardening pass. Every task now:
#   - Distinguishes permanent failures (Order.DoesNotExist -> no retry)
#     from transient ones (gateway/connection issues -> retry with backoff)
#   - Uses retry_backoff=True instead of a fixed 60s delay (Celery's
#     built-in exponential backoff + jitter, not hand-rolled math)
#   - Logs success, not just failure
#   - Formats currency consistently as {value:,.2f}
#   - Order imported at module level -- verified no circular import
#     (orders/models.py does not import notifications anywhere)

import hashlib
import logging
import uuid
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, F, OuterRef, Subquery, IntegerField, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import Product
from inventory.models import Stock
from users.models import User
from orders.models import DeliveryQuoteRequest, Order
from config.celery import TASK_RETRY_KWARGS as RETRY_KWARGS
from notifications.catalog import EVENT_CATALOG, EventType
from notifications.models import Notification, NotificationDeliveryAttempt
from notifications.services import NotificationEngineService, keyed_digest, normalize_phone
logger = logging.getLogger(__name__)

# Defense-in-depth: any task building a message longer than this gets
# truncated automatically, rather than each new task needing to
# remember to cap itself individually.
MAX_SMS_LENGTH = 1000
MAX_EMAIL_BODY_LENGTH = 12000
DELIVERY_LEASE_SECONDS = 120


def _claim_delivery(*, dedupe_key, defaults):
    """Claim one provider attempt without holding a database lock during I/O."""
    now = timezone.now()
    with transaction.atomic():
        notification, _ = Notification.objects.select_for_update().get_or_create(
            dedupe_key=dedupe_key,
            defaults=defaults,
        )
        if notification.status in {Notification.Status.SENT, Notification.Status.SUPPRESSED}:
            return notification, None, None, True
        if notification.status == Notification.Status.SENDING:
            if notification.delivery_lease_expires_at and notification.delivery_lease_expires_at > now:
                return notification, None, None, False
            notification.status = Notification.Status.MANUAL_FOLLOWUP
            notification.last_error_code = 'DELIVERY_OUTCOME_UNKNOWN'
            notification.save(update_fields=['status', 'last_error_code', 'updated_at'])
            return notification, None, None, False
        if notification.attempt_count >= notification.max_attempts:
            notification.status = Notification.Status.MANUAL_FOLLOWUP
            notification.save(update_fields=['status', 'updated_at'])
            return notification, None, None, False

        lease_token = uuid.uuid4().hex
        notification.attempt_count += 1
        notification.status = Notification.Status.SENDING
        notification.delivery_lease_token = lease_token
        notification.delivery_lease_expires_at = now + timedelta(seconds=DELIVERY_LEASE_SECONDS)
        notification.save(update_fields=[
            'attempt_count', 'status', 'delivery_lease_token',
            'delivery_lease_expires_at', 'updated_at',
        ])
        return notification, notification.attempt_count, lease_token, False


def _lock_claimed_notification(notification_id, lease_token):
    notification = Notification.objects.select_for_update().get(pk=notification_id)
    if notification.delivery_lease_token != lease_token:
        return None
    return notification


def _clear_delivery_lease(notification):
    notification.delivery_lease_token = ''
    notification.delivery_lease_expires_at = None


def _delivery_quote_status_url(quote):
    from django.urls import reverse
    from orders.delivery_quote_access import issue_delivery_quote_token
    path = reverse('delivery-quote-page', args=[quote.reference])
    url = f"{settings.SITE_BASE_URL.rstrip('/')}{path}"
    if quote.customer_id is None:
        url += f'#{issue_delivery_quote_token(quote)}'
    return url


@shared_task(name='notifications.send_delivery_quote_ready_sms', **RETRY_KWARGS)
def send_delivery_quote_ready_sms(self, quote_id: str):
    try:
        quote = DeliveryQuoteRequest.objects.select_related('branch', 'customer').get(pk=quote_id)
    except DeliveryQuoteRequest.DoesNotExist:
        return
    if quote.status not in {
        DeliveryQuoteRequest.Status.QUOTED,
        DeliveryQuoteRequest.Status.ACCEPTED,
    }:
        return
    message = (
        f'Delivery quote {quote.reference} for {quote.town} is ready. '
        f'Transport fee: KES {quote.delivery_fee:,.2f}. '
        f'Review the collection point and final total: {_delivery_quote_status_url(quote)}'
    )
    queue_sms_event(
        quote.customer_phone, message, EventType.DELIVERY_QUOTE_READY,
        'delivery_quote', quote.pk, occurrence='published', branch=quote.branch,
    )


@shared_task(name='notifications.send_delivery_quote_ready_email', **RETRY_KWARGS)
def send_delivery_quote_ready_email(self, quote_id: str):
    try:
        quote = DeliveryQuoteRequest.objects.select_related('branch', 'customer').get(pk=quote_id)
    except DeliveryQuoteRequest.DoesNotExist:
        return
    recipient = quote.customer_email or (quote.customer.email if quote.customer_id else '')
    if not recipient or quote.status not in {
        DeliveryQuoteRequest.Status.QUOTED,
        DeliveryQuoteRequest.Status.ACCEPTED,
    }:
        return
    body = (
        f'Delivery quote {quote.reference} for {quote.town} is ready.\n\n'
        f'Operator: {quote.transport_operator}\n'
        f'Collection point: {quote.collection_point}\n'
        f'Transport fee: KES {quote.delivery_fee:,.2f}\n'
        f'Expected arrival: {quote.expected_arrival}\n\n'
        f'Review current product availability and the final total: {_delivery_quote_status_url(quote)}\n\n'
        'Do not share this secure quote link.'
    )
    queue_email_event(
        recipient, f'Emporium Plug delivery quote {quote.reference}', body,
        EventType.DELIVERY_QUOTE_READY, 'delivery_quote', quote.pk,
        occurrence='published', branch=quote.branch,
    )

# Shared retry configuration -- exponential backoff with jitter,
# capped at 10 minutes between attempts. Applied consistently so a
# struggling SMS gateway or a Redis blip (both observed in this exact
# environment this session) doesn't get hammered by synchronized
# fixed-interval retries.



@shared_task(name='notifications.send_sms', **RETRY_KWARGS)
def send_sms_task(
    self, phone_number: str, message: str, event_type: str = EventType.GENERIC,
    reference_type: str = '', reference_id: str = '', dedupe_key: str = '',
):
    """Deliver one SMS with durable, idempotent attempt evidence."""
    if not phone_number or not message:
        logger.warning('SMS not queued because recipient or message was empty.')
        return False
    if len(message) > MAX_SMS_LENGTH:
        message = message[:MAX_SMS_LENGTH - 15] + '... (truncated)'
    phone = normalize_phone(phone_number)
    fingerprint = hashlib.sha256(message.encode('utf-8')).hexdigest()
    prequeued = None
    if event_type == EventType.GENERIC and not dedupe_key:
        prequeued = Notification.objects.filter(
            recipient_hash=keyed_digest(phone), message_fingerprint=fingerprint,
            status=Notification.Status.QUEUED,
        ).order_by('created_at').first()
        if prequeued:
            event_type = prequeued.event_type
            reference_type = prequeued.reference_type
            reference_id = prequeued.reference_id
            dedupe_key = prequeued.dedupe_key
    template_key, criticality, allow_whatsapp = EVENT_CATALOG.get(
        event_type, EVENT_CATALOG[EventType.GENERIC],
    )
    task_identity = getattr(self.request, 'id', '') or ''
    stable_key = dedupe_key or keyed_digest(
        f'{event_type}|{reference_type}|{reference_id}|{phone}|{fingerprint}|{task_identity}'
    )
    notification, attempt_number, lease_token, completed = _claim_delivery(
        dedupe_key=stable_key,
        defaults={
            'event_type': event_type, 'template_key': template_key,
            'criticality': criticality, 'recipient': phone,
            'recipient_hash': keyed_digest(phone),
            'reference_type': reference_type,
            'reference_id': str(reference_id or ''),
            'message_fingerprint': fingerprint,
        },
    )
    if completed:
        return True
    if attempt_number is None:
        return False

    result = NotificationEngineService.deliver_sms(phone, message)
    with transaction.atomic():
        notification = _lock_claimed_notification(notification.pk, lease_token)
        if notification is None:
            return False
        NotificationDeliveryAttempt.objects.create(
            notification=notification, attempt_number=attempt_number,
            channel=Notification.Channel.SMS, provider=result.provider,
            status=(
                NotificationDeliveryAttempt.Status.SUPPRESSED if result.suppressed
                else NotificationDeliveryAttempt.Status.SENT if result.success
                else NotificationDeliveryAttempt.Status.FAILED
            ),
            provider_message_id=result.message_id, provider_status=result.status,
            error_code=result.error_code, response_summary=result.response_summary,
        )
        if result.success:
            notification.status = (
                Notification.Status.SUPPRESSED if result.suppressed
                else Notification.Status.SENT
            )
            notification.sent_at = timezone.now()
            notification.provider_message_id = result.message_id
            notification.provider_status = result.status
            notification.last_error_code = ''
            _clear_delivery_lease(notification)
            notification.save(update_fields=[
                'status', 'sent_at', 'provider_message_id', 'provider_status',
                'last_error_code', 'delivery_lease_token',
                'delivery_lease_expires_at', 'updated_at',
            ])
            return True

    terminal = attempt_number >= notification.max_attempts or not result.retryable
    if terminal and allow_whatsapp:
        fallback = NotificationEngineService.deliver_whatsapp(phone, message)
        NotificationDeliveryAttempt.objects.create(
            notification=notification, attempt_number=attempt_number,
            channel=Notification.Channel.WHATSAPP, provider=fallback.provider,
            status=(
                NotificationDeliveryAttempt.Status.SENT
                if fallback.success else NotificationDeliveryAttempt.Status.FAILED
            ),
            provider_message_id=fallback.message_id,
            provider_status=fallback.status, error_code=fallback.error_code,
            response_summary=fallback.response_summary,
        )
        if fallback.success:
            with transaction.atomic():
                notification = _lock_claimed_notification(notification.pk, lease_token)
                if notification is None:
                    return False
                notification.status = Notification.Status.SENT
                notification.channel = Notification.Channel.WHATSAPP
                notification.sent_at = timezone.now()
                notification.provider_status = fallback.status
                notification.last_error_code = ''
                _clear_delivery_lease(notification)
                notification.save(update_fields=[
                    'status', 'channel', 'sent_at', 'provider_status',
                    'last_error_code', 'delivery_lease_token',
                    'delivery_lease_expires_at', 'updated_at',
                ])
            return True

    with transaction.atomic():
        notification = _lock_claimed_notification(notification.pk, lease_token)
        if notification is None:
            return False
        notification.provider_status = result.status
        notification.last_error_code = result.error_code
        notification.status = (
            Notification.Status.MANUAL_FOLLOWUP if terminal
            else Notification.Status.RETRY_PENDING
        )
        _clear_delivery_lease(notification)
        notification.save(update_fields=[
            'status', 'provider_status', 'last_error_code',
            'delivery_lease_token', 'delivery_lease_expires_at', 'updated_at',
        ])
    if terminal:
        return False
    raise self.retry(exc=RuntimeError(f'Retryable provider failure: {result.status}'))


def queue_sms_event(
    phone_number, message, event_type, reference_type, reference_id,
    occurrence='', branch=None, defer_until_commit=False,
):
    """Persist the event before queueing; never persist the rendered message body."""
    phone = normalize_phone(phone_number)
    if len(message) > MAX_SMS_LENGTH:
        message = message[:MAX_SMS_LENGTH - 15] + '... (truncated)'
    fingerprint = hashlib.sha256(message.encode('utf-8')).hexdigest()
    template_key, criticality, _ = EVENT_CATALOG[event_type]
    dedupe = keyed_digest(
        f'{event_type}|{reference_type}|{reference_id}|{occurrence}|{phone}'
    )
    _, created = Notification.objects.get_or_create(
        dedupe_key=dedupe,
        defaults={
            'event_type': event_type, 'template_key': template_key,
            'criticality': criticality, 'recipient': phone,
            'recipient_hash': keyed_digest(phone),
            'branch': branch,
            'reference_type': reference_type, 'reference_id': str(reference_id),
            'message_fingerprint': fingerprint,
        },
    )
    if not created:
        return False
    if defer_until_commit:
        transaction.on_commit(lambda: send_sms_task.delay(
            phone, message, event_type, reference_type, str(reference_id), dedupe,
        ))
    else:
        send_sms_task.delay(phone, message)
    return True


@shared_task(name='notifications.send_email', **RETRY_KWARGS)
def send_email_task(
    self, email_address: str, subject: str, body: str,
    event_type: str = EventType.GENERIC, reference_type: str = '',
    reference_id: str = '', dedupe_key: str = '', branch_id=None,
):
    """Deliver one durable transactional email without persisting its body."""
    recipient = str(email_address or '').strip().lower()
    try:
        validate_email(recipient)
    except ValidationError:
        logger.warning('Email not queued because the recipient address was invalid.')
        return False
    subject = str(subject or '').strip()[:180]
    body = str(body or '').strip()[:MAX_EMAIL_BODY_LENGTH]
    if not subject or not body:
        return False

    fingerprint = hashlib.sha256(f'{subject}\n{body}'.encode('utf-8')).hexdigest()
    template_key, criticality, _ = EVENT_CATALOG.get(
        event_type, EVENT_CATALOG[EventType.GENERIC],
    )
    stable_key = dedupe_key or keyed_digest(
        f'EMAIL|{event_type}|{reference_type}|{reference_id}|{recipient}|{fingerprint}'
    )
    notification, attempt_number, lease_token, completed = _claim_delivery(
        dedupe_key=stable_key,
        defaults={
            'event_type': event_type,
            'template_key': template_key.replace('.sms', '.email'),
            'channel': Notification.Channel.EMAIL,
            'criticality': criticality,
            'recipient': recipient,
            'recipient_hash': keyed_digest(recipient),
            'branch_id': branch_id,
            'reference_type': reference_type,
            'reference_id': str(reference_id or ''),
            'message_fingerprint': fingerprint,
        },
    )
    if completed:
        return True
    if attempt_number is None:
        return False

    if not settings.TRANSACTIONAL_EMAIL_ENABLED:
        provider = 'safe-email'
        provider_status = 'SUPPRESSED_DEVELOPMENT'
        attempt_status = NotificationDeliveryAttempt.Status.SUPPRESSED
        notification_status = Notification.Status.SUPPRESSED
    else:
        try:
            sent = EmailMessage(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
            ).send(fail_silently=False)
            if sent != 1:
                raise RuntimeError('Email provider did not accept exactly one message.')
            provider = 'django-email'
            provider_status = 'SENT'
            attempt_status = NotificationDeliveryAttempt.Status.SENT
            notification_status = Notification.Status.SENT
        except Exception as exc:
            with transaction.atomic():
                notification = _lock_claimed_notification(notification.pk, lease_token)
                if notification is None:
                    return False
                NotificationDeliveryAttempt.objects.create(
                    notification=notification, attempt_number=attempt_number,
                    channel=Notification.Channel.EMAIL, provider='django-email',
                    status=NotificationDeliveryAttempt.Status.FAILED,
                    error_code=type(exc).__name__[:80],
                    response_summary='Email provider did not acknowledge delivery.',
                )
                notification.status = (
                    Notification.Status.MANUAL_FOLLOWUP
                    if attempt_number >= notification.max_attempts
                    else Notification.Status.RETRY_PENDING
                )
                notification.last_error_code = type(exc).__name__[:80]
                _clear_delivery_lease(notification)
                notification.save(update_fields=[
                    'status', 'last_error_code', 'delivery_lease_token',
                    'delivery_lease_expires_at', 'updated_at',
                ])
            if attempt_number >= notification.max_attempts:
                return False
            raise self.retry(exc=RuntimeError('Transactional email delivery failed.'))

    with transaction.atomic():
        notification = _lock_claimed_notification(notification.pk, lease_token)
        if notification is None:
            return False
        NotificationDeliveryAttempt.objects.create(
            notification=notification, attempt_number=attempt_number,
            channel=Notification.Channel.EMAIL, provider=provider,
            status=attempt_status, provider_status=provider_status,
            response_summary='Message body and security codes were not retained.',
        )
        notification.status = notification_status
        notification.provider_status = provider_status
        notification.sent_at = timezone.now()
        notification.last_error_code = ''
        _clear_delivery_lease(notification)
        notification.save(update_fields=[
            'status', 'provider_status', 'sent_at', 'last_error_code',
            'delivery_lease_token', 'delivery_lease_expires_at', 'updated_at',
        ])
    return True


def queue_email_event(
    email_address, subject, body, event_type, reference_type, reference_id,
    occurrence='', branch=None,
):
    """Persist an email event before Celery delivery and deduplicate retries."""
    recipient = str(email_address or '').strip().lower()
    validate_email(recipient)
    fingerprint = hashlib.sha256(f'{subject}\n{body}'.encode('utf-8')).hexdigest()
    template_key, criticality, _ = EVENT_CATALOG[event_type]
    dedupe = keyed_digest(
        f'EMAIL|{event_type}|{reference_type}|{reference_id}|{occurrence}|{recipient}'
    )
    _, created = Notification.objects.get_or_create(
        dedupe_key=dedupe,
        defaults={
            'event_type': event_type,
            'template_key': template_key.replace('.sms', '.email'),
            'channel': Notification.Channel.EMAIL,
            'criticality': criticality,
            'recipient': recipient,
            'recipient_hash': keyed_digest(recipient),
            'branch': branch,
            'reference_type': reference_type,
            'reference_id': str(reference_id),
            'message_fingerprint': fingerprint,
        },
    )
    if not created:
        return False
    send_email_task.delay(
        recipient, subject, body, event_type, reference_type,
        str(reference_id), dedupe, branch.pk if branch else None,
    )
    return True


@shared_task(name='notifications.send_payment_confirmed_sms', **RETRY_KWARGS)
def send_payment_confirmed_sms(self, order_id: str):
    """Send payment received confirmation SMS to customer."""
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        # Permanent failure -- an order that no longer exists will never
        # exist on retry. Log and return, don't burn a retry cycle.
        logger.warning(f"send_payment_confirmed_sms: order {order_id} not found -- skipped.")
        return

    if not order.customer_phone:
        logger.warning(f"No phone on order {order_id} - SMS skipped.")
        return

    message = (
        f"Hi{' ' + order.customer_name if order.customer_name else ''}, "
        f"your payment for order {order.order_number} "
        f"(KES {order.total_payable:,.2f}) has been received. "
        f"Thank you for shopping at {order.branch.name}!"
    )

    try:
        queue_sms_event(order.customer_phone, message, EventType.PAYMENT_CONFIRMED, 'order', order.pk, branch=order.branch)
        logger.info("Payment-confirmed SMS queued for order id=%s", order.pk)
    except Exception as exc:
        logger.error("send_payment_confirmed_sms failed for order id=%s | ExceptionType=%s", order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_walkin_receipt_sms', **RETRY_KWARGS)
def send_walkin_receipt_sms(self, order_id: str):
    """Send itemized SMS receipt to walk-in customer after sale completes."""
    try:
        order = Order.objects.prefetch_related(
            'items__variant__product',
            'items__product',
        ).select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_walkin_receipt_sms: order {order_id} not found -- skipped.")
        return

    if not order.customer_phone:
        logger.warning(f"No phone on order {order_id} - receipt SMS skipped.")
        return

    item_lines = []
    for item in order.items.all():
        name = (
            item.variant.product.name if item.variant
            else item.product.name if item.product
            else "Item"
        )
        item_lines.append(f"{item.quantity}x {name}")
    items_summary = ", ".join(item_lines)

    message = (
        f"Receipt - {order.branch.name}\n"
        f"Ref: {order.order_number}\n"
        f"Items: {items_summary}\n"
        f"Subtotal: KES {order.subtotal:,.2f}\n"
        f"Discount: KES {order.discount_amount:,.2f}\n"
        f"Total: KES {order.total_payable:,.2f}\n"
        f"Payment: {order.get_payment_method_display()}\n"
        + (
            f"Cash: KES {order.amount_received:,.2f}; Change: KES {order.change_due:,.2f}\n"
            if order.amount_received is not None else ''
        )
        + "Thank you!"
    )

    try:
        queue_sms_event(order.customer_phone, message, EventType.WALKIN_RECEIPT, 'order', order.pk, branch=order.branch)
        logger.info("Walk-in receipt SMS queued for order id=%s", order.pk)
    except Exception as exc:
        logger.error("send_walkin_receipt_sms failed for order id=%s | ExceptionType=%s", order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_order_placed_sms', **RETRY_KWARGS)
def send_order_placed_sms(self, order_id: str):
    """Confirms order was received - sent immediately after checkout."""
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_order_placed_sms: order {order_id} not found -- skipped.")
        return

    phone = order.customer_phone
    if not phone:
        logger.warning(f"No phone on order {order_id} - order-placed SMS skipped.")
        return

    order_type_label = {
        'ONLINE_DELIVERY': 'delivery',
        'ONLINE_PICKUP': f"pickup (code: {order.pickup_code})",
        'WALK_IN': 'walk-in',
    }.get(order.order_type, order.order_type)

    if order.payment_method == Order.PaymentMethod.COD:
        payment_note = (
            f"Pay KES {order.total_payable:,.2f} on "
            f"{'delivery' if order.order_type == Order.OrderType.ONLINE_DELIVERY else 'collection'}."
        )
    else:
        payment_note = f"Total: KES {order.total_payable:,.2f}."

    # Configurable base URL -- settings.SITE_BASE_URL, not a hardcoded
    # placeholder or a guessed production domain.
    track_url = f"{settings.SITE_BASE_URL}/orders/{order.order_number}"

    message = (
        f"Order {order.order_number} confirmed for {order_type_label}. "
        f"{payment_note} "
        f"Track at: {track_url}"
    )

    try:
        queue_sms_event(phone, message, EventType.ORDER_PLACED, 'order', order.pk, branch=order.branch)
        logger.info("Order-placed SMS queued for order id=%s", order.pk)
    except Exception as exc:
        logger.error("send_order_placed_sms failed for order id=%s | ExceptionType=%s", order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_order_auto_cancelled_sms', **RETRY_KWARGS)
def send_order_auto_cancelled_sms(self, order_id: str):
    """
    Notifies the customer their unpaid order was auto-cancelled and
    stock released. Sent by the abandoned-checkout timeout task in
    orders/tasks.py -- never for COD orders, which are never
    auto-cancelled since they skip PENDING entirely.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_order_auto_cancelled_sms: order {order_id} not found -- skipped.")
        return

    phone = order.customer_phone
    if not phone:
        logger.warning(f"No phone on order {order_id} - cancellation SMS skipped.")
        return

    message = (
        f"Order {order.order_number} was cancelled because payment "
        f"wasn't completed in time. Your items are no longer reserved. "
        f"Feel free to place a new order anytime."
    )

    try:
        queue_sms_event(phone, message, EventType.ORDER_CANCELLED, 'order', order.pk, branch=order.branch)
        logger.info("Auto-cancellation SMS queued for order id=%s", order.pk)
    except Exception as exc:
        logger.error("send_order_auto_cancelled_sms failed for order id=%s | ExceptionType=%s", order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_delivery_status_sms', **RETRY_KWARGS)
def send_delivery_status_sms(self, order_id: str, rider_status: str):
    """Notifies customer of delivery progress updates."""
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_delivery_status_sms: order {order_id} not found -- skipped.")
        return

    phone = order.customer_phone
    if not phone:
        logger.warning(f"No phone on order {order_id} - delivery status SMS skipped.")
        return

    messages = {
        'PICKED_UP': f"Your order {order.order_number} has been picked up and is on its way!",
        'ON_THE_WAY': f"Your order {order.order_number} is out for delivery. Stay close!",
        'DELIVERED': (
            f"Your order {order.order_number} has been delivered. "
            f"If you did not receive it, call us immediately."
        ),
        'FAILED': (
            f"We couldn't deliver order {order.order_number}. "
            f"Please contact us to reschedule."
        ),
    }
    message = messages.get(rider_status)
    if not message:
        logger.warning(f"send_delivery_status_sms: unknown rider_status {rider_status!r} -- skipped.")
        return

    try:
        queue_sms_event(
            phone, message, EventType.DELIVERY_STATUS, 'order', order.pk,
            occurrence=rider_status,
            branch=order.branch,
        )
        logger.info("Delivery-status SMS queued for order id=%s | Status=%s", order.pk, rider_status)
    except Exception as exc:
        logger.error("send_delivery_status_sms failed for order id=%s | ExceptionType=%s", order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_collection_confirmed_sms', **RETRY_KWARGS)
def send_collection_confirmed_sms(self, order_id: str):
    """Confirms pickup collection to customer."""
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_collection_confirmed_sms: order {order_id} not found -- skipped.")
        return

    phone = order.customer_phone
    if not phone:
        logger.warning(f"No phone on order {order_id} - collection SMS skipped.")
        return

    message = (
        f"Order {order.order_number} collected from {order.branch.name}. "
        f"Thank you for shopping with us!"
    )

    try:
        queue_sms_event(phone, message, EventType.COLLECTION_CONFIRMED, 'order', order.pk, branch=order.branch)
        logger.info("Collection-confirmed SMS queued for order id=%s", order.pk)
    except Exception as exc:
        logger.error("send_collection_confirmed_sms failed for order id=%s | ExceptionType=%s", order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_global_low_stock_alerts_legacy')
def send_global_low_stock_alerts_legacy():
    """
    Scheduled hourly via Celery Beat.
    Finds ALL products (simple and variant) below low_stock_threshold.
    Uses annotated subqueries - one DB round trip per product type,
    not one query per product.

    List capped at MAX_ITEMS -- an SMS listing 400 low-stock products
    would blow past practical SMS length/cost limits. Summarized as
    "...and N more" instead.
    """
    MAX_ITEMS = 20

    direct_stock_sq = Stock.objects.filter(
        product=OuterRef('pk'),
        variant__isnull=True,
    ).values('product').annotate(
        total=Sum(F('quantity') - F('reserved_quantity'))
    ).values('total')

    low_simple = list(
        Product.objects.filter(
            status=Product.Status.ACTIVE,
        ).exclude(
            variants__isnull=False,
        ).annotate(
            total_stock=Coalesce(
                Subquery(direct_stock_sq, output_field=IntegerField()), 0
            )
        ).filter(
            total_stock__lte=F('low_stock_threshold')
        ).values('name', 'total_stock', 'low_stock_threshold')
    )

    variant_stock_sq = Stock.objects.filter(
        variant__product=OuterRef('pk'),
    ).values('variant__product').annotate(
        total=Sum(F('quantity') - F('reserved_quantity'))
    ).values('total')

    low_variant = list(
        Product.objects.filter(
            status=Product.Status.ACTIVE,
            variants__isnull=False,
        ).annotate(
            total_stock=Coalesce(
                Subquery(variant_stock_sq, output_field=IntegerField()), 0
            )
        ).filter(
            total_stock__lte=F('low_stock_threshold')
        ).values('name', 'total_stock', 'low_stock_threshold').distinct()
    )

    all_low = low_simple + low_variant
    if not all_low:
        logger.info("Low stock sweep: no items below threshold.")
        return

    display_items = all_low[:MAX_ITEMS]
    remaining_count = len(all_low) - len(display_items)

    alert_lines = [
        f"{p['name']} - {p['total_stock']} left "
        f"(threshold: {p['low_stock_threshold']})"
        for p in display_items
    ]
    if remaining_count > 0:
        alert_lines.append(f"...and {remaining_count} more item(s).")

    managers = User.objects.filter(
        role__in=[
            User.Role.INVENTORY_MANAGER,
            User.Role.BRANCH_MANAGER,
            User.Role.SUPER_ADMIN,
        ],
        is_active=True,
    ).exclude(phone_number='').exclude(phone_number__isnull=True)

    message = (
        f"LOW STOCK ALERT - {len(all_low)} item(s) need restocking:\n"
        + "\n".join(f"• {line}" for line in alert_lines)
    )

    for manager in managers:
        queue_sms_event(
            str(manager.phone_number), message, EventType.LOW_STOCK,
            'inventory_sweep', timezone.localdate().isoformat(),
            branch=manager.branch,
        )

    logger.info(
        f"Low stock sweep: {len(all_low)} item(s) below threshold, "
        f"alerted {managers.count()} manager(s)."
    )

@shared_task(name='notifications.send_void_processed_alert', **RETRY_KWARGS)
def send_void_processed_alert(self, order_id: str, voided_by_username: str, reason: str):
    """
    Business Context §10: 'Void processed' -> Branch manager + super admin.
    Fires immediately after a POS void commits.
    """
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_void_processed_alert: order {order_id} not found -- skipped.")
        return

    message = (
        f"VOID ALERT: Order {order.order_number} (KES {order.total_payable:,.2f}) "
        f"at {order.branch.name} was voided by {voided_by_username}. Reason: {reason}"
    )

    recipients = User.objects.filter(
        Q(role=User.Role.SUPER_ADMIN) | Q(role=User.Role.BRANCH_MANAGER, branch=order.branch),
        is_active=True,
    ).exclude(phone_number='').exclude(phone_number__isnull=True)

    for recipient in recipients:
        queue_sms_event(
            str(recipient.phone_number), message, EventType.VOID, 'order', order.pk,
            branch=order.branch,
        )

    logger.info("Void alert queued for order id=%s to %s manager(s).", order.pk, recipients.count())


@shared_task(name='notifications.send_transfer_request_alert', **RETRY_KWARGS)
def send_transfer_request_alert(self, transfer_id: str):
    """Business Context §10 pattern: notify receiving branch manager of a pending transfer."""
    from inventory.models import TransferRequest
    try:
        transfer = TransferRequest.objects.select_related('to_branch', 'from_branch', 'requested_by').get(id=transfer_id)
    except TransferRequest.DoesNotExist:
        logger.warning(f"send_transfer_request_alert: transfer {transfer_id} not found -- skipped.")
        return
    item_name = str(transfer.variant) if transfer.variant else transfer.product.name
    if transfer.status == TransferRequest.Status.DISPATCHED:
        message = (
            f"TRANSFER DISPATCHED: {transfer.quantity}x {item_name} is in transit from "
            f"{transfer.from_branch.name}. Confirm receipt only after physical verification."
        )
    else:
        message = (
            f"TRANSFER REQUEST: {transfer.quantity}x {item_name} requested from "
            f"{transfer.from_branch.name} by {transfer.requested_by.get_full_name()}. "
            f"Await dispatch before confirming receipt."
        )
    recipients = User.objects.filter(
        role=User.Role.BRANCH_MANAGER, branch=transfer.to_branch, is_active=True,
    ).exclude(phone_number='').exclude(phone_number__isnull=True)
    for r in recipients:
        queue_sms_event(
            str(r.phone_number), message, EventType.TRANSFER, 'transfer', transfer.pk,
            occurrence=transfer.status,
            branch=transfer.to_branch,
        )
    logger.info(f"Transfer request alert queued for transfer {transfer_id} to {recipients.count()} manager(s).")


@shared_task(name='notifications.send_transfer_confirmed_alert', **RETRY_KWARGS)
def send_transfer_confirmed_alert(self, transfer_id: str):
    from inventory.models import TransferRequest
    try:
        transfer = TransferRequest.objects.select_related('to_branch', 'from_branch', 'requested_by', 'confirmed_by').get(id=transfer_id)
    except TransferRequest.DoesNotExist:
        logger.warning(f"send_transfer_confirmed_alert: transfer {transfer_id} not found -- skipped.")
        return
    item_name = str(transfer.variant) if transfer.variant else transfer.product.name
    message = (
        f"TRANSFER CONFIRMED: {transfer.quantity}x {item_name} received at "
        f"{transfer.to_branch.name} by {transfer.confirmed_by.get_full_name()}. Stock updated."
    )
    phone = getattr(transfer.requested_by, 'phone_number', None)
    if phone:
        queue_sms_event(
            str(phone), message, EventType.TRANSFER, 'transfer', transfer.pk,
            occurrence='CONFIRMED',
            branch=transfer.to_branch,
        )
    logger.info(f"Transfer confirmed alert queued for transfer {transfer_id}.")


@shared_task(name='notifications.send_pickup_reminder_sms', **RETRY_KWARGS)
def send_pickup_reminder_sms(self, order_id: str):
    """24hr unresolved-pickup reminder (Business Context §8)."""
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_pickup_reminder_sms: order {order_id} not found -- skipped.")
        return
    phone = order.customer_phone
    if not phone:
        logger.warning(f"No phone on order {order_id} - pickup reminder skipped.")
        return
    message = (
        f"Reminder: your order {order.order_number} awaits pickup at "
        f"{order.branch.name}. Please collect soon or it may be released."
    )
    try:
        queue_sms_event(
            phone, message, EventType.PICKUP_REMINDER, 'order', order.pk,
            occurrence=(order.pickup_reminder_sent_at.isoformat() if order.pickup_reminder_sent_at else 'first'),
            branch=order.branch,
        )
        logger.info("Pickup reminder SMS queued for order id=%s", order.pk)
    except Exception as exc:
        logger.error("send_pickup_reminder_sms failed for order id=%s | ExceptionType=%s", order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_customer_cancelled_order_sms', **RETRY_KWARGS)
def send_customer_cancelled_order_sms(self, order_id: str):
    """Confirm a customer-requested cancellation without implying a refund."""
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning('Customer cancellation SMS skipped: order %s not found.', order_id)
        return
    if not order.customer_phone:
        return
    message = (
        f'Order {order.order_number} was cancelled as requested. '
        'Its items are no longer reserved. No payment or refund has been recorded for this cancellation.'
    )
    try:
        queue_sms_event(
            order.customer_phone, message, EventType.ORDER_CANCELLED,
            'order', order.pk, occurrence='customer-requested', branch=order.branch,
        )
    except Exception as exc:
        logger.error(
            'Customer cancellation SMS failed | OrderID=%s | ExceptionType=%s',
            order.pk, type(exc).__name__,
        )
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_order_placed_email', **RETRY_KWARGS)
def send_order_placed_email(self, order_id: str):
    """Send an order receipt/status link when checkout supplied an email."""
    try:
        order = Order.objects.select_related('branch', 'customer').get(id=order_id)
    except Order.DoesNotExist:
        return
    recipient = order.customer_email or (order.customer.email if order.customer_id else '')
    if not recipient:
        return
    from orders.checkout_access import issue_guest_order_token
    from django.urls import reverse
    path = reverse('track-order', kwargs={'order_number': order.order_number})
    token = issue_guest_order_token(order)
    tracking_url = f"{settings.SITE_BASE_URL.rstrip('/')}{path}"
    if token:
        tracking_url += f'#{token}'
    payment_note = (
        f'Pay KES {order.total_payable:,.2f} when collecting at S18.'
        if order.payment_method == Order.PaymentMethod.COD
        else f'Total payable: KES {order.total_payable:,.2f}. Payment confirmation may still be pending.'
    )
    body = (
        f'We received order {order.order_number}.\n\n'
        f'{payment_note}\n'
        f'Pickup: second floor, S18, Gaberone Plaza.\n'
        f'Track packing and collection progress: {tracking_url}\n\n'
        'Do not share your tracking link or pickup code.'
    )
    try:
        queue_email_event(
            recipient,
            f'Emporium Plug order {order.order_number}',
            body,
            EventType.ORDER_PLACED,
            'order', order.pk,
            branch=order.branch,
        )
    except Exception as exc:
        logger.error(
            'Order email could not be queued | OrderID=%s | ExceptionType=%s',
            order_id, type(exc).__name__,
        )
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_parcel_status_sms', **RETRY_KWARGS)
def send_parcel_status_sms(self, order_id: str, parcel_status: str):
    """Notify a recipient about matatu/bus parcel collection progress."""
    try:
        order = Order.objects.select_related('parcel_dispatch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning('send_parcel_status_sms: order %s not found -- skipped.', order_id)
        return
    if not order.customer_phone or not order.is_town_parcel:
        return
    dispatch = order.parcel_dispatch
    messages = {
        'DISPATCHED': (
            f'Order {order.order_number} has been sent to {order.parcel_town} through '
            f'{order.parcel_operator_name}. Parcel reference: {dispatch.parcel_reference}. '
            f'You will be contacted when it arrives.'
        ),
        'ARRIVED': (
            f'Order {order.order_number} has arrived at {order.parcel_collection_point}, '
            f'{order.parcel_town}. Reference: {dispatch.parcel_reference}. '
            f'Carry your payment confirmation and identification when collecting.'
        ),
        'COLLECTED': (
            f'Collection of order {order.order_number} at {order.parcel_town} was recorded. '
            f'Contact Emporium Plug immediately if you did not collect it.'
        ),
    }
    message = messages.get(parcel_status)
    if not message:
        logger.warning('Unknown parcel status %s for order %s.', parcel_status, order_id)
        return
    try:
        queue_sms_event(
            order.customer_phone, message, EventType.PARCEL_STATUS, 'order', order.pk,
            occurrence=parcel_status, branch=order.branch,
        )
    except Exception as exc:
        logger.error('send_parcel_status_sms failed | order=%s | type=%s', order_id, type(exc).__name__)
        raise self.retry(exc=exc)


@shared_task(name='notifications.send_pickup_ready_sms', **RETRY_KWARGS)
def send_pickup_ready_sms(self, order_id: str):
    """Notify the customer only after the ready-for-pickup transition commits."""
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning('send_pickup_ready_sms: order %s not found -- skipped.', order_id)
        return
    if not order.customer_phone:
        return
    deadline = (
        timezone.localtime(order.pickup_expires_at).strftime('%a %d %b, %I:%M %p')
        if order.pickup_expires_at else 'the stated collection deadline'
    )
    message = (
        f"Order {order.order_number} is ready at S18, second floor, Gaberone Plaza. "
        f"Pickup code: {order.pickup_code}. Collect by {deadline}. "
        "Inspect size, colour and condition before leaving."
    )
    queue_sms_event(
        str(order.customer_phone), message, EventType.PICKUP_READY, 'order', order.pk,
        branch=order.branch,
    )


@shared_task(name='notifications.send_pickup_auto_cancel_manager_alert', **RETRY_KWARGS)
def send_pickup_auto_cancel_manager_alert(self, order_id: str):
    """Notify managers when a pickup passes its configured collection deadline."""
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_pickup_auto_cancel_manager_alert: order {order_id} not found -- skipped.")
        return
    message = (
        f"PICKUP AUTO-CANCELLED: Order {order.order_number} at {order.branch.name} "
        f"was never collected and has been auto-cancelled. Stock restored."
    )
    recipients = User.objects.filter(
        Q(role=User.Role.SUPER_ADMIN) | Q(role=User.Role.BRANCH_MANAGER, branch=order.branch),
        is_active=True,
    ).exclude(phone_number='').exclude(phone_number__isnull=True)
    for r in recipients:
        queue_sms_event(
            str(r.phone_number), message, EventType.ORDER_CANCELLED, 'order', order.pk,
            occurrence='manager-pickup-expiry',
            branch=order.branch,
        )
    logger.info("Pickup auto-cancel alert queued for order id=%s to %s manager(s).", order.pk, recipients.count())
@shared_task(name='notifications.send_delivery_dispute_manager_alert', **RETRY_KWARGS)
def send_delivery_dispute_manager_alert(self, order_id: str, customer_text: str):
    """§10: 'Rider marked delivered, customer flagged non-receipt' -> Branch manager."""
    try:
        order = Order.objects.select_related('branch').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning(f"send_delivery_dispute_manager_alert: order {order_id} not found -- skipped.")
        return
    message = (
        f"DELIVERY DISPUTE: Customer for order {order.order_number} at {order.branch.name} "
        f"did not confirm receipt. Reply: \"{customer_text[:100]}\". Please investigate."
    )
    recipients = User.objects.filter(
        role=User.Role.BRANCH_MANAGER, branch=order.branch, is_active=True,
    ).exclude(phone_number='').exclude(phone_number__isnull=True)
    for r in recipients:
        queue_sms_event(
            str(r.phone_number), message, EventType.DELIVERY_DISPUTE, 'order', order.pk,
            branch=order.branch,
        )
    logger.info("Delivery dispute alert queued for order id=%s to %s manager(s).", order.pk, recipients.count())

    # apps/notifications/tasks.py — append after send_delivery_dispute_manager_alert
@shared_task(name='notifications.send_shift_variance_alert', **RETRY_KWARGS)
def send_shift_variance_alert(self, reconciliation_id: int):
    """§11 'Cash drawer shortfall' / §10 'Cash discrepancy on shift reconciliation' -> Branch manager + super admin."""
    from reports.models import ShiftReconciliation
    try:
        rec = ShiftReconciliation.objects.select_related('branch', 'cashier').get(id=reconciliation_id)
    except ShiftReconciliation.DoesNotExist:
        logger.warning(f"send_shift_variance_alert: reconciliation {reconciliation_id} not found -- skipped.")
        return
    direction = 'over' if rec.cash_variance > 0 else 'short'
    message = (
        f"CASH VARIANCE: {rec.cashier.get_full_name() or rec.cashier.username} at "
        f"{rec.branch.name} is KES {abs(rec.cash_variance):,.2f} {direction} "
        f"(expected {rec.expected_cash:,.2f}, counted {rec.actual_cash:,.2f})."
    )
    recipients = User.objects.filter(
        Q(role=User.Role.SUPER_ADMIN) | Q(role=User.Role.BRANCH_MANAGER, branch=rec.branch),
        is_active=True,
    ).exclude(phone_number='').exclude(phone_number__isnull=True)
    for r in recipients:
        queue_sms_event(
            str(r.phone_number), message, EventType.SHIFT_VARIANCE,
            'shift_reconciliation', rec.pk,
            branch=rec.branch,
        )
    logger.info(f"Shift variance alert queued for reconciliation {reconciliation_id} to {recipients.count()} manager(s).")
