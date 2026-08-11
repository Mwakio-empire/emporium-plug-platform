from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from branches.models import Branch
from users.models import User
from core.context_processors import build_whatsapp_url

from .cart_services import UnifiedSessionCartService
from .delivery_quote_access import issue_delivery_quote_token, resolve_delivery_quote_token
from .delivery_quote_services import DeliveryQuoteService
from .models import DeliveryQuoteRequest
from .checkout_views import _checkout_response


def _message(exc):
    messages = getattr(exc, 'messages', None)
    return messages[0] if messages else str(exc)


def _customer_for_request(request):
    if not request.user.is_authenticated:
        return None
    if not request.user.is_active or request.user.role != User.Role.CUSTOMER:
        raise PermissionError
    return request.user


def accessible_delivery_quote(request, reference):
    customer = _customer_for_request(request)
    if customer is not None:
        return DeliveryQuoteRequest.objects.filter(
            reference=reference, customer=customer,
        ).first()
    token = request.headers.get('X-Delivery-Quote-Token', '')
    quote = resolve_delivery_quote_token(token)
    if quote is None or quote.reference != reference or quote.customer_id is not None:
        return None
    return quote


def quote_payload(quote):
    is_open = quote.status in {
        DeliveryQuoteRequest.Status.REQUESTED,
        DeliveryQuoteRequest.Status.REVIEWING,
    }
    return {
        'reference': quote.reference,
        'status': quote.status,
        'status_label': quote.get_status_display(),
        'county': quote.county,
        'town': quote.town,
        'customer_phone': quote.customer_phone,
        'preferred_collection_area': quote.preferred_collection_area,
        'cart_snapshot': quote.cart_snapshot,
        'requested_subtotal': str(quote.requested_subtotal),
        'response_due_at': quote.response_due_at.isoformat(),
        'overdue': bool(is_open and timezone.now() > quote.response_due_at),
        'transport_operator': quote.transport_operator,
        'collection_point': quote.collection_point,
        'delivery_fee': str(quote.delivery_fee),
        'expected_arrival': quote.expected_arrival,
        'quoted_at': quote.quoted_at.isoformat() if quote.quoted_at else None,
        'expires_at': quote.expires_at.isoformat() if quote.expires_at else None,
        'order_number': quote.order.order_number if quote.order_id else None,
        'whatsapp_url': build_whatsapp_url(
            f'Hello Emporium Plug, please help me with delivery quote {quote.reference} '
            f'for {quote.town}, {quote.county}.'
        ),
    }


class DeliveryQuoteCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'delivery_quote_create'

    def post(self, request):
        try:
            _customer_for_request(request)
        except PermissionError:
            return Response(
                {'error': 'Only customer accounts may request a delivery quote.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        cart = UnifiedSessionCartService(request)
        if cart.is_empty():
            return Response(
                {'error': 'Your cart is empty. Add products before requesting a delivery quote.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        branch = Branch.objects.filter(pk=cart.cart_branch_id, is_active=True).first()
        if branch is None:
            return Response(
                {'error': 'We could not find an available shop for this cart.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            quote = DeliveryQuoteService.create_request(
                request=request,
                branch=branch,
                customer_name=request.data.get('customer_name'),
                customer_phone=request.data.get('customer_phone'),
                customer_email=request.data.get('customer_email'),
                county=request.data.get('county'),
                town=request.data.get('town'),
                preferred_collection_area=request.data.get('preferred_collection_area'),
                notes=request.data.get('notes'),
            )
        except ValidationError as exc:
            return Response({'error': _message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = quote_payload(quote)
        response['status_url'] = f'/orders/delivery-quotes/{quote.reference}/'
        if quote.customer_id is None:
            response['access_token'] = issue_delivery_quote_token(quote)
        return Response(response, status=status.HTTP_201_CREATED)


class DeliveryQuoteStatusView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'delivery_quote_status'

    def get(self, request, reference):
        try:
            quote = accessible_delivery_quote(request, reference)
        except PermissionError:
            return Response(
                {'error': 'Only customer accounts may access customer delivery quotes.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if quote is None:
            return Response({'error': 'Delivery quote not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(quote_payload(quote))


def _totals_payload(totals):
    return {
        'regular_price_total': str(totals['regular_price_total']),
        'product_discount_amount': str(totals['product_discount_amount']),
        'subtotal': str(totals['subtotal']),
        'discount_amount': str(totals['coupon_discount_amount']),
        'delivery_fee': str(totals['delivery_fee']),
        'total_payable': str(totals['total_payable']),
        'coupon_code': totals['coupon_code'],
    }


class DeliveryQuoteAcceptView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'delivery_quote_accept'

    def post(self, request, reference):
        try:
            quote = accessible_delivery_quote(request, reference)
        except PermissionError:
            return Response(
                {'error': 'Only customer accounts may accept customer delivery quotes.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if quote is None:
            return Response({'error': 'Delivery quote not found.'}, status=status.HTTP_404_NOT_FOUND)
        coupon_code = request.data.get('coupon_code', '')
        if request.data.get('preview_only') is True:
            try:
                if quote.status != DeliveryQuoteRequest.Status.QUOTED:
                    raise ValidationError('This delivery quote is not ready for acceptance.')
                if not quote.expires_at or quote.expires_at <= timezone.now():
                    raise ValidationError('This delivery quote has expired. Request a new quote before paying.')
                totals = DeliveryQuoteService.current_totals(
                    quote=quote, coupon_code=coupon_code,
                )
            except ValidationError as exc:
                return Response({'error': _message(exc)}, status=status.HTTP_409_CONFLICT)
            return Response(_totals_payload(totals))
        if request.data.get('confirmed') is not True:
            return Response(
                {'error': 'Review and confirm the current total before placing the order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            order, totals, replayed = DeliveryQuoteService.accept_and_create_order(
                quote=quote,
                expected_total=request.data.get('expected_total'),
                coupon_code=coupon_code,
            )
        except ValidationError as exc:
            current = getattr(exc, 'current_totals', None)
            payload = {'error': _message(exc)}
            if current is not None:
                payload.update(_totals_payload(current))
                payload['requires_confirmation'] = True
            return Response(payload, status=status.HTTP_409_CONFLICT)
        payload = _checkout_response(order, replayed=replayed)
        payload.update(_totals_payload(totals))
        return Response(
            payload,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )


class DeliveryQuoteDeclineView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'delivery_quote_accept'

    def post(self, request, reference):
        try:
            quote = accessible_delivery_quote(request, reference)
        except PermissionError:
            return Response({'error': 'Only customer accounts may manage customer delivery quotes.'}, status=status.HTTP_403_FORBIDDEN)
        if quote is None:
            return Response({'error': 'Delivery quote not found.'}, status=status.HTTP_404_NOT_FOUND)
        if request.data.get('confirmed') is not True:
            return Response({'error': 'Confirm that you no longer need this quote.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            declined = DeliveryQuoteService.decline(quote=quote)
        except ValidationError as exc:
            return Response({'error': _message(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(quote_payload(declined))
