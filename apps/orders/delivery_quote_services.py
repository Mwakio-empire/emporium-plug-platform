from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import logging
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from users.models import User
from users.identifiers import normalize_phone_number

from catalog.models import Product, ProductVariant, QuantityPriceTier
from catalog.pricing import QuantityPricingService
from inventory.services import InventoryService
from logistics.location_services import TownSelectionService

from .cart_services import UnifiedSessionCartService
from .checkout_access import checkout_actor, ensure_checkout_session_hash
from .models import (
    DeliveryQuoteClosure, DeliveryQuoteRequest, DeliveryQuoteStatusHistory,
    Order, OrderItem, OrderStatusHistory,
)


NAIROBI = ZoneInfo('Africa/Nairobi')
OPENING_TIME = time(8, 0)
CLOSING_TIME = time(18, 0)
RESPONSE_MINUTES = 30
QUOTE_VALID_HOURS = 24
logger = logging.getLogger(__name__)


class DeliveryQuoteService:
    """Own quote timing and state transitions before an order exists."""

    @staticmethod
    def _is_open_date(day):
        if day.weekday() > 5:
            return False
        return not DeliveryQuoteClosure.objects.filter(date=day, is_active=True).exists()

    @classmethod
    def _next_opening(cls, value):
        local = value.astimezone(NAIROBI)
        while True:
            if cls._is_open_date(local.date()):
                opens = datetime.combine(local.date(), OPENING_TIME, tzinfo=NAIROBI)
                closes = datetime.combine(local.date(), CLOSING_TIME, tzinfo=NAIROBI)
                if local < opens:
                    return opens
                if local < closes:
                    return local
            local = datetime.combine(local.date() + timedelta(days=1), OPENING_TIME, tzinfo=NAIROBI)

    @classmethod
    def response_due_at(cls, requested_at=None):
        cursor = cls._next_opening(requested_at or timezone.now())
        remaining = timedelta(minutes=RESPONSE_MINUTES)
        while remaining:
            closes = datetime.combine(cursor.date(), CLOSING_TIME, tzinfo=NAIROBI)
            available = closes - cursor
            if remaining <= available:
                return cursor + remaining
            remaining -= available
            cursor = cls._next_opening(
                datetime.combine(cursor.date() + timedelta(days=1), OPENING_TIME, tzinfo=NAIROBI)
            )
        return cursor

    @classmethod
    @transaction.atomic
    def create_request(
        cls, *, request, branch, customer_name, customer_phone, county_code,
        preferred_collection_area, town_id=None, use_custom_town=False,
        custom_town='', customer_email='', notes='', now=None,
    ):
        cart = UnifiedSessionCartService(request)
        if cart.is_empty():
            raise ValidationError('Your cart is empty. Add products before requesting a delivery quote.')
        if cart.cart_branch_id and cart.cart_branch_id != branch.pk:
            raise ValidationError('Your cart availability changed. Return to your cart and try again.')
        stock_check = cart.revalidate_stock(branch=branch)
        if not stock_check['valid']:
            raise ValidationError('Some cart quantities are no longer available. Review your cart and try again.')
        destination = TownSelectionService.resolve(
            county_code=county_code,
            town_id=town_id,
            use_custom_town=use_custom_town,
            custom_town=custom_town,
        )
        name = str(customer_name or '').strip()
        county_name = destination.county_name
        town_name = destination.town_name
        area = str(preferred_collection_area or '').strip()
        if not name:
            raise ValidationError('Enter the recipient name.')
        if not area:
            raise ValidationError('Enter the preferred collection area.')
        if len(name) > 100 or len(county_name) > 80 or len(town_name) > 100 or len(area) > 160:
            raise ValidationError('One or more delivery details are too long.')
        try:
            phone = normalize_phone_number(customer_phone)
        except ValueError as exc:
            raise ValidationError(str(exc)) from None
        email = str(customer_email or '').strip().lower()
        if email:
            validate_email(email)
        cart_items = cart.get_cart_items_extended()
        snapshot = []
        for item in cart_items:
            snapshot.append({
                'type': item['type'],
                'product_id': item['product'].pk,
                'variant_id': item['variant'].pk if item['variant'] else None,
                'name': item['product'].name,
                'variant': str(item['variant']) if item['variant'] else '',
                'quantity': int(item['quantity']),
                'display_unit_price': str(item['price']),
                'regular_unit_price': str(item['regular_price']),
                'pricing_source': item['pricing_source'],
            })
        customer = request.user if request.user.is_authenticated else None
        requested_at = now or timezone.now()
        quote = DeliveryQuoteRequest.objects.create(
            branch=branch,
            customer=customer,
            guest_session_hash=ensure_checkout_session_hash(request),
            customer_phone=phone,
            customer_name=name,
            customer_email=email,
            county=county_name,
            town=town_name,
            preferred_collection_area=area,
            notes=str(notes or '').strip()[:1000],
            cart_snapshot=snapshot,
            requested_subtotal=cart.get_total_financial_cost(),
            response_due_at=cls.response_due_at(requested_at),
        )
        DeliveryQuoteStatusHistory.objects.create(
            quote=quote,
            old_status='',
            new_status=DeliveryQuoteRequest.Status.REQUESTED,
            changed_by=customer,
            note='Customer requested a staff-verified town parcel quote.',
        )
        return quote

    @staticmethod
    def _validate_staff(quote, staff):
        if (
            not staff
            or not staff.is_active
            or staff.role not in {User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN}
        ):
            raise ValidationError(
                'An active branch manager or super admin is required to review this quote.'
            )
        if staff.role != User.Role.SUPER_ADMIN and staff.branch_id != quote.branch_id:
            raise ValidationError('Staff may review delivery quotes only for their own branch.')

    @classmethod
    @transaction.atomic
    def start_review(cls, *, quote, staff, now=None):
        locked = DeliveryQuoteRequest.objects.select_for_update().get(pk=quote.pk)
        cls._validate_staff(locked, staff)
        if locked.status == DeliveryQuoteRequest.Status.REVIEWING:
            return locked
        if locked.status != DeliveryQuoteRequest.Status.REQUESTED:
            raise ValidationError('Only a requested delivery quote can enter review.')
        locked.status = DeliveryQuoteRequest.Status.REVIEWING
        locked.review_started_at = now or timezone.now()
        locked.reviewed_by = staff
        locked.save(update_fields=['status', 'review_started_at', 'reviewed_by', 'updated_at'])
        DeliveryQuoteStatusHistory.objects.create(
            quote=locked,
            old_status=DeliveryQuoteRequest.Status.REQUESTED,
            new_status=DeliveryQuoteRequest.Status.REVIEWING,
            changed_by=staff,
            note='Staff began reviewing the route and transport fee.',
        )
        return locked

    @classmethod
    @transaction.atomic
    def publish(
        cls, *, quote, staff, transport_operator, collection_point,
        delivery_fee, expected_arrival, now=None,
    ):
        locked = DeliveryQuoteRequest.objects.select_for_update().get(pk=quote.pk)
        cls._validate_staff(locked, staff)
        if locked.status not in {
            DeliveryQuoteRequest.Status.REQUESTED,
            DeliveryQuoteRequest.Status.REVIEWING,
        }:
            raise ValidationError(
                f'A {locked.get_status_display().lower()} delivery quote cannot be published.'
            )
        operator = str(transport_operator or '').strip()
        point = str(collection_point or '').strip()
        arrival = str(expected_arrival or '').strip()
        if not operator or not point or not arrival:
            raise ValidationError(
                'Enter the transport operator, exact collection point and expected arrival.'
            )
        try:
            fee = Decimal(delivery_fee).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError('Enter a valid transport fee.') from None
        if fee < 0:
            raise ValidationError('Transport fee cannot be negative.')
        published_at = now or timezone.now()
        old_status = locked.status
        locked.status = DeliveryQuoteRequest.Status.QUOTED
        locked.reviewed_by = staff
        locked.review_started_at = locked.review_started_at or published_at
        locked.transport_operator = operator
        locked.collection_point = point
        locked.delivery_fee = fee
        locked.expected_arrival = arrival
        locked.quoted_at = published_at
        locked.expires_at = published_at + timedelta(hours=QUOTE_VALID_HOURS)
        locked.save(update_fields=[
            'status', 'reviewed_by', 'review_started_at', 'transport_operator',
            'collection_point', 'delivery_fee', 'expected_arrival', 'quoted_at',
            'expires_at', 'updated_at',
        ])
        DeliveryQuoteStatusHistory.objects.create(
            quote=locked,
            old_status=old_status,
            new_status=DeliveryQuoteRequest.Status.QUOTED,
            changed_by=staff,
            note='Staff published verified town parcel terms for customer review.',
        )
        quote_id = str(locked.pk)
        transaction.on_commit(lambda: cls._queue_ready_notifications(quote_id))
        return locked

    @staticmethod
    def _queue_ready_notifications(quote_id):
        from notifications.tasks import (
            send_delivery_quote_ready_email, send_delivery_quote_ready_sms,
        )
        for channel, task in (
            ('SMS', send_delivery_quote_ready_sms),
            ('email', send_delivery_quote_ready_email),
        ):
            try:
                task.delay(quote_id)
            except Exception as exc:
                logger.error(
                    'Delivery quote committed but notification could not be queued | '
                    'QuoteID=%s | Channel=%s | ExceptionType=%s',
                    quote_id, channel, type(exc).__name__,
                )

    @staticmethod
    def _live_lines(quote):
        active_tiers = QuantityPriceTier.objects.filter(is_active=True).order_by('minimum_quantity')
        loaded = []
        product_quantities = {}
        for snapshot in quote.cart_snapshot:
            quantity = int(snapshot.get('quantity') or 0)
            if quantity <= 0:
                raise ValidationError('This quote contains an invalid product quantity.')
            if snapshot.get('type') == 'variant':
                item = ProductVariant.objects.select_related('product').prefetch_related(
                    Prefetch('product__quantity_price_tiers', queryset=active_tiers),
                ).filter(
                    pk=snapshot.get('variant_id'), is_active=True,
                    product__status=Product.Status.ACTIVE,
                ).first()
                if item is None or item.product_id != snapshot.get('product_id'):
                    raise ValidationError('A quoted product option is no longer available.')
                product = item.product
                variant = item
            else:
                product = Product.objects.prefetch_related(
                    Prefetch('quantity_price_tiers', queryset=active_tiers),
                ).filter(
                    pk=snapshot.get('product_id'), status=Product.Status.ACTIVE,
                ).first()
                if product is None:
                    raise ValidationError('A quoted product is no longer available.')
                variant = None
            product_quantities[product.pk] = product_quantities.get(product.pk, 0) + quantity
            loaded.append((product, variant, quantity))

        from marketing.services import PromotionService
        lines = []
        for product, variant, quantity in loaded:
            if product_quantities[product.pk] < product.minimum_order_quantity:
                raise ValidationError(
                    f'{product.name} requires at least {product.minimum_order_quantity} units.'
                )
            regular = variant.effective_price if variant else product.price
            current = (
                PromotionService.resolve_live_variant_market_price(variant)
                if variant else product.price
            )
            price_quote = QuantityPricingService.quote(
                product=product,
                regular_unit_price=regular,
                current_unit_price=current,
                product_quantity=product_quantities[product.pk],
            )
            lines.append({
                'product': product,
                'variant': variant,
                'quantity': quantity,
                'price_quote': price_quote,
            })
        return lines

    @classmethod
    def current_totals(cls, *, quote, coupon_code=''):
        lines = cls._live_lines(quote)
        subtotal = sum(
            (line['price_quote'].unit_price * line['quantity'] for line in lines),
            Decimal('0.00'),
        )
        regular_total = sum(
            (line['price_quote'].regular_unit_price * line['quantity'] for line in lines),
            Decimal('0.00'),
        )
        coupon_discount = Decimal('0.00')
        normalized_coupon = str(coupon_code or '').strip().upper()
        if normalized_coupon:
            from marketing.services import PromotionService
            coupon_discount = PromotionService.validate_coupon_preview(
                coupon_code=normalized_coupon,
                subtotal=subtotal,
                branch=quote.branch,
                customer=quote.customer,
                pricing_sources=(line['price_quote'].source for line in lines),
            )
        return {
            'lines': lines,
            'regular_price_total': regular_total,
            'product_discount_amount': max(Decimal('0.00'), regular_total - subtotal),
            'subtotal': subtotal,
            'coupon_discount_amount': coupon_discount,
            'delivery_fee': quote.delivery_fee,
            'total_payable': subtotal - coupon_discount + quote.delivery_fee,
            'coupon_code': normalized_coupon,
        }

    @classmethod
    @transaction.atomic
    def accept_and_create_order(
        cls, *, quote, expected_total, coupon_code='', now=None,
    ):
        locked = DeliveryQuoteRequest.objects.select_for_update(of=('self',)).select_related(
            'branch', 'customer', 'order',
        ).get(pk=quote.pk)
        if locked.order_id:
            order = Order.objects.prefetch_related('items').get(pk=locked.order_id)
            regular_total = sum(
                (item.regular_unit_price * item.quantity for item in order.items.all()),
                Decimal('0.00'),
            )
            existing_coupon = getattr(order, 'coupon_redemption', None)
            return order, {
                'lines': [],
                'regular_price_total': regular_total,
                'product_discount_amount': max(Decimal('0.00'), regular_total - order.subtotal),
                'subtotal': order.subtotal,
                'coupon_discount_amount': order.discount_amount,
                'delivery_fee': order.delivery_fee,
                'total_payable': order.total_payable,
                'coupon_code': existing_coupon.coupon.code if existing_coupon else '',
            }, True
        current_time = now or timezone.now()
        if locked.status != DeliveryQuoteRequest.Status.QUOTED:
            raise ValidationError('This delivery quote is not ready for acceptance.')
        if not locked.expires_at or locked.expires_at <= current_time:
            locked.status = DeliveryQuoteRequest.Status.EXPIRED
            locked.save(update_fields=['status', 'updated_at'])
            raise ValidationError('This delivery quote has expired. Request a new quote before paying.')
        totals = cls.current_totals(quote=locked, coupon_code=coupon_code)
        try:
            confirmed_total = Decimal(expected_total).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError('Review and confirm the current total before placing the order.') from None
        if confirmed_total != totals['total_payable']:
            error = ValidationError('The order total changed. Review the updated amount and confirm again.')
            error.current_totals = totals
            raise error

        actor = checkout_actor(locked.customer)
        parcel_weight = sum(
            (Decimal(str(line['product'].weight or 0)) * line['quantity'] for line in totals['lines']),
            Decimal('0.00'),
        )
        order = Order.objects.create(
            branch=locked.branch,
            customer=locked.customer,
            order_type=Order.OrderType.ONLINE_DELIVERY,
            sales_channel=Order.SalesChannel.WEBSITE,
            customer_phone=locked.customer_phone,
            customer_name=locked.customer_name,
            customer_email=locked.customer_email,
            delivery_address=locked.collection_point,
            delivery_fee=locked.delivery_fee,
            parcel_weight_kg=parcel_weight,
            parcel_county_name=locked.county,
            parcel_town=locked.town,
            parcel_collection_point=locked.collection_point,
            parcel_operator_name=locked.transport_operator,
            payment_method=Order.PaymentMethod.MPESA_STK,
            notes=locked.notes,
            processed_by=actor,
            status=Order.Status.PENDING,
            guest_session_hash=locked.guest_session_hash,
            subtotal=totals['subtotal'],
            total_payable=totals['subtotal'] + locked.delivery_fee,
        )
        for line in totals['lines']:
            price_quote = line['price_quote']
            item = OrderItem(
                order=order,
                product=line['product'] if line['variant'] is None else None,
                variant=line['variant'],
                quantity=line['quantity'],
                unit_price=price_quote.unit_price,
                regular_unit_price=price_quote.regular_unit_price,
                pricing_source=price_quote.source,
                quantity_tier_minimum=price_quote.tier_minimum,
                quantity_discount_percentage=price_quote.discount_percentage,
            )
            item.full_clean()
            item.save()
            InventoryService.reserve_stock(
                branch=locked.branch,
                quantity=line['quantity'],
                triggered_by=actor,
                variant=line['variant'],
                product=line['product'] if line['variant'] is None else None,
                reference_number=order.order_number,
                note=f'Reserved after customer accepted delivery quote {locked.reference}.',
            )
        if totals['coupon_code']:
            from marketing.services import PromotionService
            order = PromotionService.validate_and_apply_coupon_campaign(
                order, totals['coupon_code'],
            )
        OrderStatusHistory.objects.create(
            order=order,
            old_status='',
            new_status=Order.Status.PENDING,
            note=f'Delivery quote {locked.reference} accepted; awaiting M-Pesa payment.',
            changed_by=actor,
        )
        locked.status = DeliveryQuoteRequest.Status.ACCEPTED
        locked.accepted_at = current_time
        locked.order = order
        locked.save(update_fields=['status', 'accepted_at', 'order', 'updated_at'])
        DeliveryQuoteStatusHistory.objects.create(
            quote=locked,
            old_status=DeliveryQuoteRequest.Status.QUOTED,
            new_status=DeliveryQuoteRequest.Status.ACCEPTED,
            changed_by=locked.customer,
            note=f'Customer accepted the current total; order {order.order_number} was created.',
        )
        from .online_services import OnlineOrderService
        transaction.on_commit(
            lambda: OnlineOrderService._trigger_order_placed_notifications(str(order.pk))
        )
        return order, totals, False

    @classmethod
    @transaction.atomic
    def decline(cls, *, quote, now=None):
        locked = DeliveryQuoteRequest.objects.select_for_update().get(pk=quote.pk)
        if locked.status == DeliveryQuoteRequest.Status.DECLINED:
            return locked
        if locked.status not in {
            DeliveryQuoteRequest.Status.REQUESTED,
            DeliveryQuoteRequest.Status.REVIEWING,
            DeliveryQuoteRequest.Status.QUOTED,
        }:
            raise ValidationError('This delivery quote can no longer be declined.')
        old_status = locked.status
        locked.status = DeliveryQuoteRequest.Status.DECLINED
        locked.declined_at = now or timezone.now()
        locked.save(update_fields=['status', 'declined_at', 'updated_at'])
        DeliveryQuoteStatusHistory.objects.create(
            quote=locked,
            old_status=old_status,
            new_status=DeliveryQuoteRequest.Status.DECLINED,
            changed_by=locked.customer,
            note='Customer declined the delivery quote; no order was created.',
        )
        return locked
