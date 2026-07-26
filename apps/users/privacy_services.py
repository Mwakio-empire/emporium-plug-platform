from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction

from analytics.models import AuditLog
from marketing.models import ProductReview, ReturnRequest
from notifications.models import Notification
from notifications.services import keyed_digest
from orders.models import Order
from users.models import PrivacyRequest, User


class PrivacyRequestReviewService:
    @classmethod
    @transaction.atomic
    def resolve(cls, *, request_id, actor, password, outcome, response_note):
        if actor.role != User.Role.SUPER_ADMIN or not actor.is_active:
            raise ValidationError('Only an active super-admin may resolve privacy requests.')
        if not actor.check_password(password or ''):
            raise ValidationError('Manager password confirmation failed.')
        if outcome not in {PrivacyRequest.Status.COMPLETED, PrivacyRequest.Status.REJECTED}:
            raise ValidationError('Select a valid final outcome.')
        note = str(response_note or '').strip()
        if len(note) < 8:
            raise ValidationError('Record at least eight characters explaining the outcome.')
        privacy_request = PrivacyRequest.objects.select_for_update().get(pk=request_id)
        if privacy_request.status in {
            PrivacyRequest.Status.COMPLETED, PrivacyRequest.Status.REJECTED,
        }:
            raise ValidationError('This privacy request is already closed.')
        privacy_request.status = outcome
        privacy_request.response_note = note
        privacy_request.handled_by = actor
        privacy_request.handled_at = timezone.now()
        privacy_request.save(update_fields=[
            'status', 'response_note', 'handled_by', 'handled_at', 'updated_at',
        ])
        return privacy_request


class PersonalDataExportService:
    """Produce a scoped, machine-readable export without secrets or other users' data."""

    @classmethod
    def build(cls, user):
        orders = Order.objects.filter(customer=user).select_related(
            'branch', 'delivery_zone', 'pickup_slot',
        ).prefetch_related('items__product', 'items__variant__product')
        order_rows = []
        for order in orders:
            payment = getattr(order, 'mpesa_payment', None)
            order_rows.append({
                'order_number': order.order_number,
                'branch': order.branch.name,
                'order_type': order.order_type,
                'status': order.status,
                'customer_name': order.customer_name,
                'customer_phone': order.customer_phone,
                'customer_email': order.customer_email,
                'delivery_address': order.delivery_address,
                'payment_method': order.payment_method,
                'payment_reference': order.payment_reference,
                'subtotal': order.subtotal,
                'discount_amount': order.discount_amount,
                'delivery_fee': order.delivery_fee,
                'total_payable': order.total_payable,
                'created_at': order.created_at,
                'items': [
                    {
                        'name': (
                            item.variant.product.name if item.variant_id
                            else item.product.name
                        ),
                        'quantity': item.quantity,
                        'unit_price': item.unit_price,
                        'total_price': item.total_price,
                    }
                    for item in order.items.all()
                ],
                'mpesa_payment': (
                    {
                        'status': payment.status,
                        'amount': payment.amount,
                        'receipt_number': payment.mpesa_receipt_number,
                        'phone_number': payment.phone_number,
                        'confirmation_method': payment.confirmation_method,
                        'created_at': payment.created_at,
                    } if payment else None
                ),
            })

        return {
            'generated_at': timezone.now(),
            'scope_note': (
                'This export includes records linked to this account. Guest orders '
                'placed without an account require separate identity verification.'
            ),
            'account': {
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone_number': user.phone_number,
                'email': user.email,
                'date_joined': user.date_joined,
                'activated_at': user.activated_at,
                'last_login': user.last_login,
            },
            'orders': order_rows,
            'reviews': list(ProductReview.objects.filter(customer=user).values(
                'product__name', 'rating', 'comment', 'is_approved',
                'moderation_reason', 'created_at',
            )),
            'returns': list(ReturnRequest.objects.filter(order__customer=user).values(
                'order__order_number', 'quantity', 'reason', 'status',
                'item_condition', 'stock_disposition', 'refund_status',
                'decision_reason', 'created_at', 'decided_at',
            )),
            'notifications': list(Notification.objects.filter(
                recipient_hash=keyed_digest(str(user.phone_number)),
            ).values(
                'event_type', 'channel', 'status', 'reference_type',
                'reference_id', 'created_at', 'sent_at',
            )),
            'account_activity': list(AuditLog.objects.filter(user=user).values(
                'action_type', 'description', 'ip_address', 'timestamp',
            )),
            'privacy_requests': list(user.privacy_requests.values(
                'request_type', 'details', 'status', 'created_at',
                'handled_at', 'response_note',
            )),
        }
