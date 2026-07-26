import hashlib
import json
import uuid

from django.core import signing
from django.core.exceptions import ValidationError
from django.utils.crypto import salted_hmac

from users.models import User

from .models import Order


GUEST_ORDER_TOKEN_SALT = 'orders.guest-access.v1'
GUEST_ORDER_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7


def ensure_checkout_session_hash(request):
    if request.user.is_authenticated:
        return ''
    if not request.session.session_key:
        request.session.create()
    return salted_hmac(
        'orders.guest-session.v1', request.session.session_key,
    ).hexdigest()


def parse_idempotency_key(raw_value):
    try:
        return uuid.UUID(str(raw_value))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError('A valid checkout idempotency key is required.')


def checkout_request_fingerprint(data):
    fields = {
        key: data.get(key) or ''
        for key in (
            'branch_id', 'order_type', 'customer_phone', 'customer_name',
            'customer_email', 'delivery_zone_id', 'parcel_destination_id', 'delivery_address',
            'pickup_slot_id', 'payment_method', 'coupon_code', 'notes',
            'confirmed',
        )
    }
    encoded = json.dumps(fields, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def order_matches_checkout_owner(order, request, guest_session_hash=''):
    if request.user.is_authenticated:
        return order.customer_id == request.user.pk
    return order.customer_id is None and order.guest_session_hash == guest_session_hash


def issue_guest_order_token(order):
    if order.customer_id is not None:
        return None
    return signing.dumps(
        {'order_number': order.order_number},
        salt=GUEST_ORDER_TOKEN_SALT,
        compress=True,
    )


def resolve_guest_order_token(token, *, max_age=GUEST_ORDER_TOKEN_MAX_AGE_SECONDS):
    try:
        payload = signing.loads(token, salt=GUEST_ORDER_TOKEN_SALT, max_age=max_age)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
    return Order.objects.filter(
        order_number=payload.get('order_number'), customer__isnull=True,
    ).first()


def checkout_actor(customer):
    return customer or User.get_system_account()
