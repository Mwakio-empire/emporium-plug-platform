# apps/orders/online_services.py
#
# All field references verified against apps/orders/models.py and
# apps/logistics/models.py as shared this session.
#
# Parcel destination and pickup slot are persisted on Order and are mutually
# exclusive. Walk-in orders cannot carry either fulfilment choice.

import secrets
import string
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Order, OrderItem, OrderStatusHistory
from orders.cart_services import UnifiedSessionCartService
from inventory.services import InventoryService
from inventory.models import StockAuditLog
from users.identifiers import normalize_phone_number
from logistics.parcel_services import ParcelPricingService

from .checkout_access import checkout_actor


class OnlineOrderService:
    """
    Creates online orders (delivery or pickup) from the storefront cart.
    Mirrors the atomic guarantees of POSSalesService -- nothing partial
    is ever saved if any step fails.
    """

    @staticmethod
    @transaction.atomic
    def create_order(
        *,
        request,
        branch,
        customer,
        order_type: str,
        customer_phone: str,
        customer_name: str = '',
        customer_email: str = '',
        parcel_destination=None,
        delivery_address: str = '',
        pickup_slot=None,
        notes: str = '',
        payment_method: str = Order.PaymentMethod.MPESA_STK,
        coupon_code: str = None,
        idempotency_key=None,
        request_fingerprint: str = '',
        guest_session_hash: str = '',
        sales_channel: str = Order.SalesChannel.WEBSITE,
        processed_by=None,
    ) -> Order:
        """
        Creates an online order from the session cart.

        Args:
            request:          Current request -- used to access the session cart
            branch:            Branch instance the order is placed against
            customer:          User instance placing the order
            order_type:        Order.OrderType.ONLINE_DELIVERY or ONLINE_PICKUP
            customer_phone:    Mandatory -- verified field on Order
            customer_name:     Optional -- verified field on Order
            parcel_destination: Verified parcel collection route selected by the customer.
            delivery_address:  Verified field on Order (TextField, blank=True)
            pickup_slot:       PickupSlot instance (logistics app) -- persisted
                               directly on Order.pickup_slot.
            notes:             Verified field on Order (TextField, blank=True)

        Flow:
          1. Validate cart is not empty
          2. Validate delivery/pickup info based on order_type
          3. Hard stock re-validation across all cart items
          4. Create Order in PENDING state
          5. Generate pickup_code if ONLINE_PICKUP
          6. Create OrderItems with prices locked at this exact moment
          7. Deduct stock atomically per item via InventoryService
          8. Write initial OrderStatusHistory entry
          9. Flush cart after DB commit (transaction.on_commit)
          10. Trigger order-placed SMS after DB commit (transaction.on_commit)

        Raises:
            ValidationError: empty cart, missing delivery/pickup info,
                             stock changed since cart was built
        """
        cart = UnifiedSessionCartService(request)
        actor = processed_by or checkout_actor(customer)
        if sales_channel not in Order.SalesChannel.values:
            raise ValidationError('Unknown sales channel.')
        if sales_channel == Order.SalesChannel.WHATSAPP_ASSISTED:
            from users.models import User
            if not processed_by or processed_by.role not in User.PRIVILEGED_ROLES:
                raise ValidationError('A signed-in staff member must record an assisted order.')

        if idempotency_key:
            existing = Order.objects.filter(
                checkout_idempotency_key=idempotency_key,
            ).first()
            if existing:
                owner_matches = (
                    existing.customer_id == customer.pk
                    if customer is not None else
                    existing.customer_id is None
                    and existing.guest_session_hash == guest_session_hash
                )
                if not owner_matches or existing.checkout_request_fingerprint != request_fingerprint:
                    raise ValidationError(
                        'This checkout key was already used for another request.'
                    )
                return existing

        # Guard: only MPESA_STK or COD (cash on delivery/collection) are
        # valid for online checkout. PAYBILL and CASH are walk-in-specific
        # (counter payment via POSSalesService) -- kept as distinct
        # PaymentMethod values so reports never conflate an instant
        # walk-in cash sale with a deferred online COD order.
        allowed_online_payment_methods = [
            Order.PaymentMethod.MPESA_STK,
            Order.PaymentMethod.COD,
        ]
        if payment_method not in allowed_online_payment_methods:
            raise ValidationError(
                f"payment_method must be one of {allowed_online_payment_methods} "
                f"for online orders."
            )

        # 1. Guard: empty cart
        if cart.is_empty():
            raise ValidationError("Cannot place an order with an empty cart.")
        if cart.cart_branch_id and cart.cart_branch_id != branch.pk:
            raise ValidationError(
                "The checkout branch does not match the branch selected for this cart."
            )

        # 2. Guard: delivery/pickup info required per order_type, AND
        # enforced as mutually exclusive -- a delivery order can never
        # carry a pickup_slot and vice versa. This is the actual fix for
        # the KNOWN-LIMITATION: not just persisting the choice, but
        # guaranteeing it's never set on the wrong order_type.
        if order_type == Order.OrderType.ONLINE_DELIVERY:
            if not parcel_destination:
                raise ValidationError(
                    "A parcel destination must be selected for parcel orders."
                )
            if payment_method != Order.PaymentMethod.MPESA_STK:
                raise ValidationError(
                    "Parcel-to-town orders must be prepaid using M-Pesa."
                )
            if pickup_slot is not None:
                raise ValidationError(
                    "A delivery order cannot also have a pickup slot."
                )

        if order_type == Order.OrderType.ONLINE_PICKUP:
            if not branch.offers_customer_pickup:
                raise ValidationError(
                    "Customer pickup is not enabled for this branch. Select the approved S18 collection branch."
                )
            if not pickup_slot:
                raise ValidationError(
                    "A pickup time slot must be selected for pickup orders."
                )
            if parcel_destination is not None:
                raise ValidationError(
                    "A pickup order cannot also have a parcel destination."
                )

        if order_type == Order.OrderType.WALK_IN:
            if parcel_destination is not None or pickup_slot is not None:
                raise ValidationError(
                    "Walk-in orders cannot have a parcel destination or pickup slot."
                )

        # 3. Hard stock re-validation -- catches stock changes since the
        # cart was built (uses UnifiedSessionCartService.revalidate_stock(),
        # which now uses Sum() aggregation per the Block E fixes)
        stock_check = cart.revalidate_stock(branch=branch)
        if not stock_check['valid']:
            stock_issues = "; ".join(
                f"{i['name']}: requested {i['requested']}, "
                f"only {i['available']} available"
                for i in stock_check['issues']
            )
            minimum_issues = "; ".join(
                f"add {i['shortfall']} more {i['name']} "
                f"(minimum {i['required']})"
                for i in stock_check.get('minimum_order_issues', [])
            )
            details = "; ".join(part for part in (stock_issues, minimum_issues) if part)
            raise ValidationError(
                f"Please review your cart before checkout: {details}."
            )

        parcel_weight = None
        delivery_fee = Decimal('0.00')
        if parcel_destination is not None:
            quoted_destination, parcel_weight, delivery_fee = ParcelPricingService.quote(
                destination_id=parcel_destination.pk, cart=cart,
            )
            parcel_destination = quoted_destination

        # Lock route and commercial details. Approved S18 cash pickup starts
        # processing immediately; M-Pesa orders remain pending until paid.
        is_cash_on_delivery = payment_method == Order.PaymentMethod.COD
        initial_status = (
            Order.Status.PROCESSING if is_cash_on_delivery else Order.Status.PENDING
        )

        try:
            normalized_phone = normalize_phone_number(customer_phone)
        except ValueError as exc:
            raise ValidationError(str(exc))

        order = Order.objects.create(
            branch=branch,
            customer=customer,
            order_type=order_type,
            sales_channel=sales_channel,
            customer_phone=normalized_phone,
            customer_name=customer_name.strip(),
            customer_email=customer_email.strip().lower(),
            delivery_address=delivery_address.strip(),
            delivery_fee=delivery_fee,
            parcel_destination=parcel_destination,
            parcel_weight_kg=parcel_weight,
            parcel_county_name=(parcel_destination.county.name if parcel_destination else ''),
            parcel_town=(parcel_destination.town if parcel_destination else ''),
            parcel_collection_point=(parcel_destination.collection_point if parcel_destination else ''),
            parcel_operator_name=(parcel_destination.operator_name if parcel_destination else ''),
            pickup_slot=pickup_slot,
            payment_method=payment_method,
            notes=notes,
            processed_by=actor,
            status=initial_status,
            checkout_idempotency_key=idempotency_key,
            checkout_request_fingerprint=request_fingerprint,
            guest_session_hash=guest_session_hash,
        )

          # 5. Generate a collection code only for pickup fulfilment. The
          # selected pickup slot is already stored on the order above.
        if order_type == Order.OrderType.ONLINE_PICKUP:
            order.pickup_code = OnlineOrderService._generate_pickup_code()
            order.save(update_fields=['pickup_code'])

        running_subtotal = Decimal('0.00')
        cart_items = cart.get_cart_items_extended()

        for item in cart_items:
            # 6. Create order item -- price locked at this exact moment.
            # variant and product are both nullable on OrderItem, matching
            # the verified model. OrderItem.clean() enforces exactly one
            # of the two is set.
            # cart_services.py's get_cart_items_extended() ALWAYS populates
            # item['product'] -- for a 'variant' type entry, it holds the
            # variant's PARENT product (used for cart display, e.g.
            # "Shirt - Size: Large"). But OrderItem.clean() requires
            # EXACTLY one of variant/product to be set. Passing
            # item['product'] straight through for a variant item would
            # set BOTH fields and fail validation. Only pass product when
            # this cart entry is actually a simple product.
            order_item = OrderItem(
                order=order,
                variant=item['variant'],
                product=item['product'] if item['type'] == 'product' else None,
                quantity=item['quantity'],
                unit_price=item['price'],
                regular_unit_price=item['regular_price'],
                pricing_source=item['pricing_source'],
                quantity_tier_minimum=item['quantity_tier_minimum'],
                quantity_discount_percentage=item['quantity_discount_percentage'],
            )
            order_item.full_clean()
            order_item.save()
            running_subtotal += order_item.total_price

            # 7. Reserve stock. Physical on-hand is consumed only when the
            # payment/fulfilment policy reaches its commitment point.
            InventoryService.reserve_stock(
                branch=branch,
                quantity=int(item['quantity']),
                triggered_by=actor,
                variant=item['variant'],
                product=item['product'] if item['type'] == 'product' else None,
                reference_number=order.order_number,
                note='Reserved by online checkout.',
            )

        order.subtotal = running_subtotal
        order.total_payable = running_subtotal + delivery_fee
        order.save(update_fields=['subtotal', 'total_payable'])
        # Coupon applied AFTER subtotal is locked — validate_and_apply_coupon_campaign
        # reads order.subtotal, so it must run after the line above. Raises
        # ValidationError on invalid/expired/threshold-miss codes, which
        # propagates and rolls back this entire @transaction.atomic block
        # (stock deductions included) — an invalid code must never silently
        # produce an uncoupled order.
        if coupon_code and any(item['wholesale_applied'] for item in cart_items):
            raise ValidationError(
                'A quantity price is already applied. Coupons cannot be combined with quantity pricing.'
            )
        if coupon_code:
            from marketing.services import PromotionService
            order = PromotionService.validate_and_apply_coupon_campaign(order, coupon_code)
        # 8. Status history -- old_status='' for the initial entry.
        # new_status matches whatever initial_status was actually used
        # (PROCESSING for COD, PENDING for MPESA_STK).
        OrderStatusHistory.objects.create(
            order=order,
            old_status='',
            new_status=initial_status,
            note=(
                f"{'WhatsApp-assisted' if sales_channel == Order.SalesChannel.WHATSAPP_ASSISTED else 'Online'} pickup order recorded -- Cash on collection, "
                f"payment due at "
                f"{'delivery' if order_type == Order.OrderType.ONLINE_DELIVERY else 'pickup'}."
                if is_cash_on_delivery else
                f"{'WhatsApp-assisted' if sales_channel == Order.SalesChannel.WHATSAPP_ASSISTED else 'Online'} {order_type} order placed."
            ),
            changed_by=actor,
        )

        # 9 & 10. Post-commit only -- never fire if the transaction rolls back
        order_id_str = str(order.id)
        transaction.on_commit(lambda: cart.flush_entire_cart())
        transaction.on_commit(
            lambda: OnlineOrderService._trigger_order_placed_notifications(order_id_str)
        )

        return order

    @staticmethod
    def _trigger_order_placed_notifications(order_id: str):
        """
        Isolated in its own method so nothing in the notification path can
        ever break order creation -- this runs after the transaction has
        already committed successfully via transaction.on_commit().

        Broadened to catch Exception, not just ImportError: .delay() talks
        to the Celery broker (Redis in this project), and this exact
        environment has already hit a live Redis connection failure this
        session (apps/core/signals.py). If the broker is down at checkout
        time, .delay() can raise a connection error -- the order must
        still be considered successfully placed either way.
        """
        import logging
        from notifications.tasks import send_order_placed_email, send_order_placed_sms
        for channel, task in (
            ('SMS', send_order_placed_sms),
            ('email', send_order_placed_email),
        ):
            try:
                task.delay(order_id)
            except Exception as exc:
                logging.getLogger(__name__).error(
                    'Order %s committed, but its %s notification could not be queued | ExceptionType=%s',
                    order_id, channel, type(exc).__name__,
                )

    @staticmethod
    def _generate_pickup_code():
        """Generate a cryptographically secure six-character collection code."""
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(6))
