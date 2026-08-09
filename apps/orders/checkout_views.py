import hashlib
import logging
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response
from users.models import User

from .models import Order
from .online_services import OnlineOrderService
from branches.models import Branch
from logistics.models import PickupSlot, DeliveryAssignment
from logistics.parcel_services import ParcelPricingService
from payments.services import MpesaDarajaService
from payments.models import MpesaTransaction
from .checkout_access import (
    checkout_request_fingerprint,
    ensure_checkout_session_hash,
    issue_guest_order_token,
    order_matches_checkout_owner,
    parse_idempotency_key,
    resolve_guest_order_token,
)
from .cart_services import UnifiedSessionCartService
from .cancellation_services import CustomerOrderCancellationService
from marketing.services import PromotionService

logger = logging.getLogger(__name__)

PAYMENT_RESERVATION_MINUTES = 30


def _customer_status_note(order, status_value):
    """Return approved customer copy; never expose operational history notes."""
    if (
        status_value == Order.Status.CANCELLED
        and (order.void_reason or '').startswith(
            CustomerOrderCancellationService.REASON_PREFIX,
        )
    ):
        return 'You cancelled this order and its reserved items were released.'
    messages = {
        Order.Status.PENDING: (
            'Your order was placed. Complete the M-Pesa prompt to confirm payment.'
            if order.payment_method == Order.PaymentMethod.MPESA_STK
            else 'Your order was placed.'
        ),
        Order.Status.PAYMENT_CONFIRMED: 'Your payment was confirmed.',
        Order.Status.PROCESSING: (
            'Your pickup order was received. Pay when collecting at S18.'
            if order.payment_method == Order.PaymentMethod.COD
            else 'Your order was received and is being prepared.'
        ),
        Order.Status.PACKING: 'Your items are being packed.',
        Order.Status.PACKED: 'Your order has been packed.',
        Order.Status.READY_FOR_PICKUP: 'Your order is ready for collection at S18.',
        Order.Status.CANCELLED: 'Payment was not completed, so this order was cancelled.',
        Order.Status.COLLECTED: 'Your order was collected.',
        Order.Status.CUSTOMER_CONFIRMED: 'You confirmed that the order was received.',
        Order.Status.RETURNED: 'This order was returned.',
    }
    return messages.get(status_value, 'Your order status was updated.')


class CheckoutPaymentOrderThrottle(SimpleRateThrottle):
    """Limit payment retries per protected order, never per shared proxy IP."""

    scope = 'checkout_payment_order'

    def get_cache_key(self, request, view):
        order_number = str(request.data.get('order_number') or '').strip().upper()
        if not order_number:
            return None
        if request.user.is_authenticated:
            owner_key = f'user:{request.user.pk}'
        else:
            token = str(
                request.data.get('access_token')
                or request.headers.get('X-Guest-Order-Token')
                or ''
            )
            if not token:
                return None
            owner_key = 'guest:' + hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]
        ident = f'{owner_key}:{order_number}'
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class OrderCancellationThrottle(CheckoutPaymentOrderThrottle):
    scope = 'order_cancel'

# FIX 1: explicit whitelist -- CheckoutInitView is a customer-facing API.
# WALK_IN orders must only ever be created by POSSalesService from the
# physical POS terminal (cashier, manager-PIN discount flow). Any other
# order_type value is also rejected, not silently coerced.
ALLOWED_ONLINE_ORDER_TYPES = [
    Order.OrderType.ONLINE_PICKUP,
]

ALLOWED_ONLINE_PAYMENT_METHODS = [
    Order.PaymentMethod.MPESA_STK,
    Order.PaymentMethod.COD,
]


def _coupon_discount(
    coupon_code, subtotal, *, branch, customer=None, pricing_sources=(),
):
    if not coupon_code:
        return Decimal('0.00')
    return PromotionService.validate_coupon_preview(
        coupon_code=coupon_code,
        subtotal=subtotal,
        branch=branch,
        customer=customer,
        pricing_sources=pricing_sources,
    )


def _validation_message(exc):
    messages = getattr(exc, 'messages', None)
    return messages[0] if messages else str(exc)


def _checkout_customer(request):
    if not request.user.is_authenticated:
        return None
    if not request.user.is_active or request.user.role != User.Role.CUSTOMER:
        raise PermissionError
    return request.user


def _accessible_order(request, order_number, *, required_status=None):
    if request.user.is_authenticated:
        if not request.user.is_active or request.user.role != User.Role.CUSTOMER:
            raise PermissionError
        queryset = Order.objects.filter(
            customer=request.user, order_number=order_number,
        )
    else:
        token = request.headers.get('X-Guest-Order-Token')
        if not token:
            token = (
                request.data.get('access_token')
                if request.method == 'POST'
                else request.query_params.get('token')
            )
        order = resolve_guest_order_token(token or '')
        if order is None or order.order_number != order_number:
            return None
        queryset = Order.objects.filter(pk=order.pk)
    if required_status is not None:
        queryset = queryset.filter(status=required_status)
    return queryset.first()


def _checkout_response(order, *, replayed=False):
    next_step = (
        'initiate_payment'
        if order.payment_method == Order.PaymentMethod.MPESA_STK
        else 'confirmed'
    )
    guest_token = issue_guest_order_token(order)
    payload = {
        'order_number': order.order_number,
        'subtotal': str(order.subtotal),
        'discount_amount': str(order.discount_amount),
        'total_payable': str(order.total_payable),
        'delivery_fee': str(order.delivery_fee),
        'status': order.status,
        'payment_method': order.payment_method,
        'next_step': next_step,
        'replayed': replayed,
        'tracking_url': reverse(
            'track-order', kwargs={'order_number': order.order_number},
        ),
    }
    if guest_token:
        payload['guest_access_token'] = guest_token
        payload['tracking_url'] += f'#{guest_token}'
        payload['account_creation_url'] = reverse('accounts:signup')
    return payload


class CheckoutInitView(APIView):
    """
    POST /api/checkout/init/
    Step 1 -- creates the order, deducts stock, returns order number.
    MPESA_STK orders still need Step 2 (STK push). COD orders are fully
    confirmed at this step -- nothing further to pay online.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        try:
            user = _checkout_customer(request)
        except PermissionError:
            return Response({'error': 'Only customer accounts may use checkout.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            idempotency_key = parse_idempotency_key(
                request.headers.get('Idempotency-Key') or data.get('idempotency_key')
            )
        except ValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        guest_session_hash = ensure_checkout_session_hash(request)
        request_fingerprint = checkout_request_fingerprint(data)
        existing = Order.objects.filter(checkout_idempotency_key=idempotency_key).first()
        if existing:
            if not order_matches_checkout_owner(existing, request, guest_session_hash):
                return Response({'error': 'This checkout session expired. Refresh the page and review your cart before trying again.'}, status=status.HTTP_409_CONFLICT)
            if existing.checkout_request_fingerprint != request_fingerprint:
                return Response({'error': 'Your checkout details changed. Refresh the page, review the order, and confirm again.'}, status=status.HTTP_409_CONFLICT)
            return Response(_checkout_response(existing, replayed=True), status=status.HTTP_200_OK)

        # --- FIX 1: validate order_type before anything else ---
        order_type = data.get('order_type')
        if order_type not in ALLOWED_ONLINE_ORDER_TYPES:
            return Response(
                {
                    'error': (
                        'Public checkout currently supports S18 pickup only. '
                        'Town parcel orders start with a verified delivery quote. Request one from checkout before paying.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Validate payment_method (COD support) ---
        payment_method = data.get('payment_method', Order.PaymentMethod.MPESA_STK)
        if payment_method not in ALLOWED_ONLINE_PAYMENT_METHODS:
            return Response(
                {
                    'error': (
                        f"payment_method must be one of "
                        f"{ALLOWED_ONLINE_PAYMENT_METHODS}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Resolve branch ---
        try:
            branch = Branch.objects.get(id=data.get('branch_id'), is_active=True)
        except Branch.DoesNotExist:
            return Response(
                {'error': 'We could not find an available shop for this cart. Return to your cart or contact us for help.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve the approved parcel route for town-collection orders.
        parcel_destination = None
        if order_type == Order.OrderType.ONLINE_DELIVERY:
            try:
                parcel_destination, _, _ = ParcelPricingService.quote(
                    destination_id=data.get('parcel_destination_id'),
                    cart=UnifiedSessionCartService(request),
                )
            except ValidationError as exc:
                return Response(
                    {'error': _validation_message(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not str(data.get('customer_name', '')).strip():
                return Response(
                    {'error': 'Enter the parcel recipient name.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # --- Resolve pickup slot (pickup orders only) ---
        pickup_slot = None
        if order_type == Order.OrderType.ONLINE_PICKUP:
            if not branch.offers_customer_pickup:
                return Response(
                    {'error': 'Customer pickup is available only from the approved S18 collection branch.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                pickup_slot = PickupSlot.objects.filter(
                    id=data.get('pickup_slot_id'),
                    branch=branch,
                    is_active=True,
                ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now())).first()
                if pickup_slot is None:
                    raise PickupSlot.DoesNotExist
            except PickupSlot.DoesNotExist:
                return Response(
                    {'error': 'Invalid or inactive pickup slot for this branch.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        customer_email = data.get('customer_email', '').strip().lower()
        if customer_email:
            try:
                validate_email(customer_email)
            except ValidationError:
                return Response({'error': 'Enter a valid email address.'}, status=status.HTTP_400_BAD_REQUEST)

        if data.get('confirmed') is not True:
            return Response(
                {'error': 'Confirm that you have reviewed and agree to place this order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            order_type == Order.OrderType.ONLINE_DELIVERY
            and payment_method != Order.PaymentMethod.MPESA_STK
        ):
            return Response(
                {'error': 'Parcel-to-town orders must be prepaid using M-Pesa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = OnlineOrderService.create_order(
                request=request,
                branch=branch,
                customer=user,
                order_type=order_type,
                customer_phone=data.get(
                    'customer_phone', str(user.phone_number) if user else '',
                ),
                customer_name=data.get(
                    'customer_name', user.get_full_name() if user else '',
                ),
                customer_email=customer_email or (user.email if user and user.email else ''),
                parcel_destination=parcel_destination,
                delivery_address=data.get('delivery_address', ''),
                pickup_slot=pickup_slot,
                notes=data.get('notes', ''),
                payment_method=payment_method,
                coupon_code=data.get('coupon_code', '').strip() or None,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                guest_session_hash=guest_session_hash,
            )
        except IntegrityError:
            order = Order.objects.filter(checkout_idempotency_key=idempotency_key).first()
            if (
                not order
                or not order_matches_checkout_owner(order, request, guest_session_hash)
                or order.checkout_request_fingerprint != request_fingerprint
            ):
                return Response({'error': 'We could not confirm whether that order was already placed. Check your order tracking before trying again.'}, status=status.HTTP_409_CONFLICT)
            return Response(_checkout_response(order, replayed=True), status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'error': _validation_message(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(
                "Checkout initialization failed | ExceptionType=%s",
                type(e).__name__,
            )
            return Response(
                {'error': 'We could not place your order. No payment was requested. Please try again or contact us for help.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(_checkout_response(order), status=status.HTTP_201_CREATED)


class CheckoutPreviewView(APIView):
    """Revalidate the cart and return the amount that checkout would charge."""

    permission_classes = [AllowAny]

    def post(self, request):
        try:
            _checkout_customer(request)
        except PermissionError:
            return Response(
                {'error': 'Only customer accounts may use checkout.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = request.data
        try:
            branch = Branch.objects.get(pk=data.get('branch_id'), is_active=True)
        except Branch.DoesNotExist:
            return Response({'error': 'We could not find an available shop for this cart. Return to your cart or contact us for help.'}, status=status.HTTP_400_BAD_REQUEST)

        order_type = data.get('order_type')
        if order_type not in ALLOWED_ONLINE_ORDER_TYPES:
            return Response(
                {
                    'error': (
                        'Public checkout currently supports S18 pickup only. '
                        'Request a verified town-parcel quote from checkout before paying.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery_fee = Decimal('0.00')
        parcel_weight = None
        if order_type == Order.OrderType.ONLINE_DELIVERY:
            try:
                _, parcel_weight, delivery_fee = ParcelPricingService.quote(
                    destination_id=data.get('parcel_destination_id'),
                    cart=UnifiedSessionCartService(request),
                )
            except ValidationError as exc:
                return Response(
                    {'error': _validation_message(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            if not branch.offers_customer_pickup:
                return Response(
                    {'error': 'Customer pickup is available only from the approved S18 collection branch.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            slot = PickupSlot.objects.filter(
                pk=data.get('pickup_slot_id'), branch=branch, is_active=True,
            ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now())).first()
            if slot is None:
                return Response(
                    {'error': 'Select an active pickup time for this branch.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        cart = UnifiedSessionCartService(request)
        if cart.is_empty():
            return Response({'error': 'Your cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)
        if cart.cart_branch_id and cart.cart_branch_id != branch.pk:
            return Response(
                {'error': 'Your cart availability changed. Return to your cart and try checkout again.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        stock_check = cart.revalidate_stock(branch=branch)
        if not stock_check['valid']:
            minimum_issues = stock_check.get('minimum_order_issues', [])
            if minimum_issues:
                detail = '; '.join(
                    f"add {item['shortfall']} more {item['name']} "
                    f"(minimum {item['required']})"
                    for item in minimum_issues
                )
                return Response(
                    {
                        'error': f'Please review your cart before checkout: {detail}.',
                        'minimum_order_issues': minimum_issues,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {'error': 'Some cart quantities are no longer available.', 'stock_issues': stock_check['issues']},
                status=status.HTTP_409_CONFLICT,
            )
        subtotal = cart.get_total_financial_cost()
        cart_items = cart.get_cart_items_extended()
        wholesale_pricing_applied = any(item['wholesale_applied'] for item in cart_items)
        if data.get('coupon_code', '').strip() and wholesale_pricing_applied:
            return Response(
                {
                    'error': 'A quantity price is already applied. Coupons cannot be combined with quantity pricing.',
                    'coupon_valid': False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            discount = _coupon_discount(
                data.get('coupon_code', '').strip(), subtotal,
                branch=branch,
                customer=(request.user if request.user.is_authenticated else None),
                pricing_sources=(item['pricing_source'] for item in cart_items),
            )
        except ValidationError as exc:
            return Response(
                {'error': _validation_message(exc), 'coupon_valid': False},
                status=status.HTTP_400_BAD_REQUEST,
            )
        total = subtotal - discount + delivery_fee
        regular_price_total = sum(
            (Decimal(item['regular_price']) * int(item['quantity']) for item in cart_items),
            Decimal('0.00'),
        )
        product_discount_amount = max(
            Decimal('0.00'), regular_price_total - subtotal,
        )
        return Response({
            'subtotal': str(subtotal),
            'regular_price_total': str(regular_price_total),
            'product_discount_amount': str(product_discount_amount),
            'discount_amount': str(discount),
            'delivery_fee': str(delivery_fee),
            'parcel_weight_kg': str(parcel_weight) if parcel_weight is not None else None,
            'total_payable': str(total),
            'price_changes': stock_check['price_changes'],
            'coupon_valid': bool(data.get('coupon_code', '').strip()),
            'coupon_code': data.get('coupon_code', '').strip().upper(),
            'wholesale_pricing_applied': wholesale_pricing_applied,
        })


class CheckoutPaymentInitView(APIView):
    """
    POST /api/checkout/pay/
    Step 2 -- triggers M-Pesa STK push for a PENDING order.
    Verified: MpesaDarajaService.initiate_stk_push is a @classmethod,
    called correctly here without instantiation.
    """
    permission_classes = [AllowAny]
    throttle_classes = [CheckoutPaymentOrderThrottle]

    def post(self, request):
        order_number = request.data.get('order_number')
        phone = request.data.get('phone', '').strip()

        if not order_number or not phone:
            return Response(
                {'error': 'Enter your order number and M-Pesa phone number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = _accessible_order(
                request, order_number, required_status=Order.Status.PENDING,
            )
        except PermissionError:
            return Response({'error': 'Only customer accounts may use checkout.'}, status=status.HTTP_403_FORBIDDEN)
        if order is None:
            return Response(
                {'error': 'We could not start payment for this order. It may already be paid or no longer awaiting payment. Open order tracking to check.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            transaction = MpesaDarajaService.initiate_stk_push(
                order=order,
                phone_number=phone,
            )
            return Response({
                'message': 'STK push sent. Please enter your M-Pesa PIN.',
                'checkout_request_id': transaction.checkout_request_id,
            })

        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            logger.warning("STK push initiation failed | OrderID=%s", order.pk)
            return Response(
                {
                    'error': error_msg,
                    'fallback': True,
                    'message': (
                        f"Automated payment is temporarily unavailable. "
                        f"Please pay KES {order.total_payable} to Paybill "
                        f"{self._get_paybill()} Account: {order.order_number}, "
                        f"then submit your M-Pesa reference below."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @staticmethod
    def _get_paybill():
        import environ
        env = environ.Env()
        return env('MPESA_SHORTCODE', default='[PAYBILL]')


class CheckoutFallbackPaymentView(APIView):
    """
    POST /api/checkout/pay/fallback/
    Customer manually submits M-Pesa reference when STK push fails.
    Flagged for manager review -- does NOT auto-confirm.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        order_number = request.data.get('order_number', '').strip()
        mpesa_ref = request.data.get('mpesa_reference', '').strip().upper()

        if not order_number or not mpesa_ref:
            return Response(
                {'error': 'Enter your order number and M-Pesa confirmation code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = _accessible_order(
                request, order_number, required_status=Order.Status.PENDING,
            )
        except PermissionError:
            return Response({'error': 'Only customer accounts may use checkout.'}, status=status.HTTP_403_FORBIDDEN)
        if order is None:
            return Response(
                {'error': 'Order not found or already paid.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if MpesaTransaction.objects.filter(
            Q(mpesa_receipt_number=mpesa_ref) | Q(submitted_reference=mpesa_ref)
        ).exists():
            return Response(
                {'error': 'This M-Pesa reference has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment, _ = MpesaTransaction.objects.get_or_create(
            order=order,
            defaults={
                'merchant_request_id': f"FALLBACK-MERCHANT-{order.order_number}",
                'checkout_request_id': f"FALLBACK-CHECKOUT-{order.order_number}",
                'status': MpesaTransaction.Status.RECONCILIATION_REQUIRED,
                'expected_amount': order.total_payable,
                'account_reference': order.order_number,
            },
        )
        payment.submitted_reference = mpesa_ref
        if payment.status == MpesaTransaction.Status.INITIATION_FAILED:
            payment.status = MpesaTransaction.Status.RECONCILIATION_REQUIRED
        try:
            payment.save(update_fields=['submitted_reference', 'status', 'updated_at'])
        except IntegrityError:
            return Response(
                {'error': 'This M-Pesa reference has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Fallback payment reference submitted | OrderID=%s | CustomerID=%s",
            order.pk,
            request.user.pk if request.user.is_authenticated else None,
        )

        return Response({
            'message': (
                f"Reference {mpesa_ref} received. "
                f"Your order {order.order_number} will be confirmed once "
                f"our team verifies the payment. You will receive an SMS."
            ),
        })


class OrderStatusView(APIView):
    """
    GET /api/orders/{order_number}/status/
    Customer tracks their own order.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'order_status'

    def get(self, request, order_number):
        try:
            accessible = _accessible_order(request, order_number)
        except PermissionError:
            return Response({'error': 'Only customer accounts may access customer tracking.'}, status=status.HTTP_403_FORBIDDEN)
        if accessible is None:
            return Response({'error': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            order = Order.objects.prefetch_related(
                'items__product',
                # FIX 3: prefetch one level deeper -- str(item.variant)
                # internally accesses variant.product.name, which was
                # triggering a fresh query per item without this.
                'items__variant__product',
                'status_history',
            ).select_related(
                'branch',
                'mpesa_payment',
                'delivery_assignment__rider__user',
                'parcel_destination',
                'parcel_dispatch',
            ).get(pk=accessible.pk)
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # FIX 2: distinguish "no assignment yet" from "assigned but no
        # rider picked yet" instead of silently swallowing both into the
        # same bare except.
        rider_data = None
        try:
            assignment = order.delivery_assignment
        except DeliveryAssignment.DoesNotExist:
            assignment = None

        if assignment is not None:
            if assignment.rider is not None:
                rider_data = {
                    'name': assignment.rider.user.get_full_name(),
                    'status': assignment.get_status_display(),
                }
            else:
                # Assignment exists (PENDING_ASSIGNMENT) but no rider
                # picked yet -- distinct from "no assignment at all"
                rider_data = {
                    'name': None,
                    'status': assignment.get_status_display(),
                }

        can_cancel, cancellation_message = CustomerOrderCancellationService.eligibility(order)
        return Response({
            'order_number': order.order_number,
            'status': order.status,
            'order_type': order.order_type,
            'branch': order.branch.name,
            'total_payable': str(order.total_payable),
            'delivery_fee': str(order.delivery_fee),
            'delivery_address': order.delivery_address,
            'parcel': (
                {
                    'county': order.parcel_county_name,
                    'town': order.parcel_town,
                    'collection_point': order.parcel_collection_point,
                    'operator': order.parcel_operator_name,
                    'weight_kg': str(order.parcel_weight_kg),
                    'reference': (
                        order.parcel_dispatch.parcel_reference
                        if hasattr(order, 'parcel_dispatch') else None
                    ),
                }
                if order.is_town_parcel else None
            ),
            'pickup_code': order.pickup_code or None,
            'pickup_expires_at': (
                order.pickup_expires_at.isoformat()
                if order.pickup_expires_at else None
            ),
            'payment_expires_at': (
                (order.created_at + timedelta(minutes=PAYMENT_RESERVATION_MINUTES)).isoformat()
                if order.status == Order.Status.PENDING
                and order.payment_method == Order.PaymentMethod.MPESA_STK
                and getattr(order, 'mpesa_payment', None) is not None
                and order.mpesa_payment.status in {
                    MpesaTransaction.Status.INITIATING,
                    MpesaTransaction.Status.PENDING,
                    MpesaTransaction.Status.QUERY_CONFIRMED,
                }
                else None
            ),
            'can_cancel': can_cancel,
            'cancellation_deadline': (
                CustomerOrderCancellationService.deadline(order).isoformat()
                if can_cancel else None
            ),
            'cancellation_message': cancellation_message,
            'cancelled_by_customer': bool(
                order.status == Order.Status.CANCELLED
                and (order.void_reason or '').startswith(
                    CustomerOrderCancellationService.REASON_PREFIX,
                )
            ),
            'rider': rider_data,
            'status_history': [
                {
                    'status': h.new_status,
                    'message': _customer_status_note(order, h.new_status),
                    'timestamp': h.created_at.isoformat(),
                }
                for h in order.status_history.all()
            ],
            'items': [
                {
                    'name': (
                        str(item.variant) if item.variant
                        else item.product.name
                    ),
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'total': str(item.total_price),
                }
                for item in order.items.all()
            ],
        })


class CustomerOrderCancellationView(APIView):
    """POST /api/orders/{order_number}/cancel/ for the protected order owner."""

    permission_classes = [AllowAny]
    throttle_classes = [OrderCancellationThrottle]

    def post(self, request, order_number):
        if request.data.get('confirmed') is not True:
            return Response(
                {'error': 'Confirm that you want to cancel this order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            order = _accessible_order(request, order_number)
        except PermissionError:
            return Response(
                {'error': 'Only customer accounts may manage customer orders.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if order is None:
            return Response({'error': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            cancelled = CustomerOrderCancellationService.cancel(
                order=order,
                requested_by=(request.user if request.user.is_authenticated else None),
            )
        except ValidationError as exc:
            return Response(
                {'error': _validation_message(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({
            'order_number': cancelled.order_number,
            'status': cancelled.status,
            'message': 'Your order has been cancelled and its items are no longer reserved.',
        })
