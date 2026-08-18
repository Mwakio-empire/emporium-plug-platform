# apps/orders/tests/test_online_checkout.py
#
# Django's built-in test runner (TestCase, unittest-style).
# Placed at apps/orders/tests/test_online_checkout.py -- this exact path
# and filename were already anticipated in Root_Directory.md, so no new
# naming convention is being introduced here.
#
# Design choice: rather than mocking UnifiedSessionCartService (which
# was already fully tested in Block E), these tests build a REAL session
# via RequestFactory + SessionMiddleware and populate it through the
# actual cart service. This exercises the real integration between
# cart_services.py and online_services.py, not a mocked approximation
# of it -- consistent with this project's demonstrated preference for
# integration correctness over brittle mocking.
#
# The one place mocking IS used deliberately: test_partial_failure_rolls
# _back_entire_order, where InventoryService.reserve_stock is patched to
# fail on the second cart item. This is a controlled failure injection
# point for testing atomicity -- not something achievable deterministically
# in a single-threaded test any other way, since revalidate_stock() and
# the deduction loop both query fresh stock and would normally agree.

from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock
from datetime import timedelta
from django.utils import timezone
from logistics.models import KenyaCounty, ParcelDestination, PickupSlot
from marketing.models import FlashSale
from orders.models import Order, OrderItem, OrderStatusHistory
from orders.online_services import OnlineOrderService
from apps.orders.cart_services import UnifiedSessionCartService, STOREFRONT_SELECTED_BRANCH_KEY

User = get_user_model()


class OnlineCheckoutTestDataMixin:
    """
    Builds branch, customer, catalog items with stock, and logistics
    zone/slot needed across all online checkout tests.
    """

    def setUp(self):
        self.branch = Branch.objects.create(
            name="Checkout Test Branch", location="Test Location", offers_customer_pickup=True,
        )

        self.customer = User.objects.create_user(
            username='checkoutcustomer0001',
            phone_number='+254733000001',
            email='checkoutcustomer0001@test.com',
            first_name='Checkout',
            last_name='Customer',
            password='CheckoutPass123!',
            role=User.Role.CUSTOMER,
        )

        self.category = Category.objects.create(
            name="Checkout Test Category", slug="checkout-test-category",
        )

        self.product_simple = Product.objects.create(
            name="Checkout Test Kettle", slug="checkout-test-kettle",
            category=self.category, price=Decimal("1000.00"),
            weight=Decimal('1.50'),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch, product=self.product_simple, quantity=10)

        self.product_variant_parent = Product.objects.create(
            name="Checkout Test Shirt", slug="checkout-test-shirt",
            category=self.category, price=Decimal("500.00"),
            weight=Decimal('0.25'),
            status=Product.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product_variant_parent,
            attribute_name="Size", attribute_value="Large",
        )
        Stock.objects.create(branch=self.branch, variant=self.variant, quantity=8)

        self.county, _ = KenyaCounty.objects.get_or_create(code='37', defaults={'name': 'Kakamega'})
        self.parcel_destination = ParcelDestination.objects.create(
            county=self.county, town='Kakamega', collection_point='Main parcel stage',
            operator_name='Approved Test Operator', nairobi_dispatch_point='Nairobi stage',
            fee=Decimal('150.00'), included_weight_kg=Decimal('5.00'),
            additional_kg_fee=Decimal('30.00'), effective_from=timezone.localdate(),
            is_active=True,
        )
        self.pickup_slot = PickupSlot.objects.create(
            branch=self.branch, label="9:00 AM - 11:00 AM",
        )

    def _get_request_with_session(self):
        """Builds a real request with a working session -- not a mock."""
        request = RequestFactory().get('/')
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        request.session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch.pk
        request.session.save()
        return request

    def _build_cart_with_product(self, request, quantity=1):
        cart = UnifiedSessionCartService(request)
        cart.add_product(product_id=self.product_simple.id, quantity=quantity)
        return cart

    def _build_cart_with_variant(self, request, quantity=1):
        cart = UnifiedSessionCartService(request)
        cart.add_variant(variant_id=self.variant.id, quantity=quantity)
        return cart


class OrderTypeGuardTests(OnlineCheckoutTestDataMixin, TestCase):
    """Tests every validation guard in create_order() -- each one traced
    to a specific raise statement in online_services.py."""

    def test_empty_cart_raises_error(self):
        """WHAT: create_order() called with nothing in the cart
        EXPECT: ValidationError, no Order created"""
        request = self._get_request_with_session()
        orders_before = Order.objects.count()

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_DELIVERY,
                customer_phone='+254700111111',
                parcel_destination=self.parcel_destination,
                delivery_address='123 Test Street',
            )

        self.assertEqual(Order.objects.count(), orders_before)

    def test_checkout_branch_must_match_cart_branch(self):
        request = self._get_request_with_session()
        self._build_cart_with_product(request)
        other_branch = Branch.objects.create(
            name='Checkout Other Branch', location='Other Location',
        )
        with self.assertRaisesMessage(ValidationError, 'does not match'):
            OnlineOrderService.create_order(
                request=request,
                branch=other_branch,
                customer=self.customer,
                order_type=Order.OrderType.ONLINE_DELIVERY,
                customer_phone='+254700111111',
                parcel_destination=self.parcel_destination,
                delivery_address='123 Test Street',
            )

    def test_delivery_without_zone_raises_error(self):
        """WHAT: ONLINE_DELIVERY with delivery_zone=None
        EXPECT: ValidationError"""
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_DELIVERY,
                customer_phone='+254700111111',
                parcel_destination=None,
                delivery_address='123 Test Street',
            )

    def test_parcel_recipient_instructions_are_optional(self):
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        order = OnlineOrderService.create_order(
            request=request, branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_DELIVERY,
            customer_phone='+254700111111',
            parcel_destination=self.parcel_destination,
            delivery_address='   ',
        )
        self.assertEqual(order.delivery_address, '')

    def test_delivery_order_cannot_also_carry_pickup_slot(self):
        """
        WHAT: ONLINE_DELIVERY with BOTH delivery_zone and pickup_slot set
        EXPECT: ValidationError -- this is the mutual-exclusivity fix,
                not just persistence
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_DELIVERY,
                customer_phone='+254700111111',
                parcel_destination=self.parcel_destination,
                delivery_address='123 Test Street',
                pickup_slot=self.pickup_slot,
            )

    def test_pickup_without_slot_raises_error(self):
        """WHAT: ONLINE_PICKUP with pickup_slot=None
        EXPECT: ValidationError"""
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_PICKUP,
                customer_phone='+254700111111',
                pickup_slot=None,
            )

    def test_pickup_order_cannot_also_carry_delivery_zone(self):
        """
        WHAT: ONLINE_PICKUP with BOTH pickup_slot and delivery_zone set
        EXPECT: ValidationError
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_PICKUP,
                customer_phone='+254700111111',
                pickup_slot=self.pickup_slot,
                parcel_destination=self.parcel_destination,
            )

    def test_walk_in_cannot_carry_zone_or_slot(self):
        """
        WHAT: OnlineOrderService.create_order() called with order_type=WALK_IN
              but a delivery_zone is (incorrectly) passed
        EXPECT: ValidationError -- WALK_IN orders must have neither
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.WALK_IN,
                customer_phone='+254700111111',
                parcel_destination=self.parcel_destination,
            )


class SuccessfulOrderCreationTests(OnlineCheckoutTestDataMixin, TestCase):

    def test_delivery_order_persists_zone_and_fee(self):
        """
        WHAT: Successful ONLINE_DELIVERY order
        EXPECT: order.delivery_zone is the actual zone instance,
                order.delivery_fee equals zone.fee, order.pickup_slot
                is None. This is the direct proof the KNOWN-LIMITATION
                fix works -- the zone is retrievable after the fact.
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request, quantity=2)

        order = OnlineOrderService.create_order(
            request=request, branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_DELIVERY,
            customer_phone='+254700111111',
                parcel_destination=self.parcel_destination,
            delivery_address='123 Test Street',
        )

        order.refresh_from_db()
        self.assertEqual(order.parcel_destination_id, self.parcel_destination.id)
        self.assertEqual(order.delivery_fee, self.parcel_destination.fee)
        self.assertIsNone(order.pickup_slot)
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_pickup_order_persists_slot_and_generates_code(self):
        """
        WHAT: Successful ONLINE_PICKUP order
        EXPECT: order.pickup_slot is the actual slot instance,
                order.pickup_code is set and 6 characters,
                order.delivery_zone is None, delivery_fee is 0
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request, quantity=1)

        order = OnlineOrderService.create_order(
            request=request, branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254700111111',
            pickup_slot=self.pickup_slot,
        )

        order.refresh_from_db()
        self.assertEqual(order.pickup_slot_id, self.pickup_slot.id)
        self.assertIsNone(order.delivery_zone)
        self.assertEqual(order.delivery_fee, Decimal('0.00'))
        self.assertEqual(len(order.pickup_code), 6)

    def test_pickup_code_is_uppercase_alphanumeric(self):
        """
        WHAT: Generated pickup_code
        EXPECT: exactly 6 characters, all uppercase letters or digits --
                matches the format ConfirmPickupView's PickupCodeSerializer
                validates against (^[A-Z0-9]{6}$)
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        order = OnlineOrderService.create_order(
            request=request, branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254700111111',
            pickup_slot=self.pickup_slot,
        )

        import re
        self.assertRegex(order.pickup_code, r'^[A-Z0-9]{6}$')

    @patch('orders.online_services.secrets.choice', side_effect=list('A1B2C3'))
    def test_pickup_code_uses_secure_random_selection(self, mocked_choice):
        code = OnlineOrderService._generate_pickup_code()

        self.assertEqual(code, 'A1B2C3')
        self.assertEqual(mocked_choice.call_count, 6)

    def test_mixed_cart_computes_correct_subtotal(self):
        """
        WHAT: Cart with BOTH a simple product and a variant
        EXPECT: subtotal = (product.price * qty) + (variant.effective_price * qty),
                two OrderItems created -- one product, one variant
        """
        request = self._get_request_with_session()
        cart = UnifiedSessionCartService(request)
        cart.add_product(product_id=self.product_simple.id, quantity=2)
        cart.add_variant(variant_id=self.variant.id, quantity=3)

        order = OnlineOrderService.create_order(
            request=request, branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254700111111',
            pickup_slot=self.pickup_slot,
        )

        expected_subtotal = (
            self.product_simple.price * 2 + self.variant.effective_price * 3
        )
        order.refresh_from_db()
        self.assertEqual(order.subtotal, expected_subtotal)
        self.assertEqual(order.items.count(), 2)

    def test_order_status_history_entry_created(self):
        """
        WHAT: Successful order creation
        EXPECT: exactly one OrderStatusHistory row, old_status='',
                new_status=PENDING
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        order = OnlineOrderService.create_order(
            request=request, branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254700111111',
            pickup_slot=self.pickup_slot,
        )

        history = OrderStatusHistory.objects.filter(order=order)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().old_status, '')
        self.assertEqual(history.first().new_status, Order.Status.PENDING)

    def test_stock_is_reserved_after_order(self):
        """
        WHAT: Order for 3 units of a product with 10 in stock
        EXPECT: Physical on-hand remains 10 and 3 units become reserved.
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request, quantity=3)

        OnlineOrderService.create_order(
            request=request, branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254700111111',
            pickup_slot=self.pickup_slot,
        )

        stock = Stock.objects.get(branch=self.branch, product=self.product_simple)
        self.assertEqual(stock.quantity, 10)
        self.assertEqual(stock.reserved_quantity, 3)


class StockValidationTests(OnlineCheckoutTestDataMixin, TestCase):

    def test_stock_change_since_cart_built_prevents_order(self):
        """
        WHAT: Add to cart while stock=10, then stock drops to 0 before
              checkout completes (simulating another sale in between)
        EXPECT: ValidationError from revalidate_stock(), NO Order created,
                stock unchanged by this failed attempt
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request, quantity=5)

        # Simulate stock being consumed by another transaction in the meantime
        stock = Stock.objects.get(branch=self.branch, product=self.product_simple)
        stock.quantity = 0
        stock.save(update_fields=['quantity'])

        orders_before = Order.objects.count()

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_PICKUP,
                customer_phone='+254700111111',
                pickup_slot=self.pickup_slot,
            )

        self.assertEqual(Order.objects.count(), orders_before)


class AtomicityTests(OnlineCheckoutTestDataMixin, TestCase):

    @patch('orders.online_services.InventoryService.reserve_stock')
    def test_partial_failure_rolls_back_entire_order(self, mock_adjust):
        """
        WHAT: A cart with two items. InventoryService.reserve_stock is
              patched to succeed on the first item, then raise
              ValidationError on the second.
        EXPECT: The entire transaction rolls back -- NO Order and NO
                OrderItem exist afterward, even though the first item's
                creation "succeeded" before the second one failed.

        This is a deliberate failure-injection test. revalidate_stock()
        and the real deduction loop both query fresh stock and would
        normally agree in a single-threaded test, so there is no other
        deterministic way to prove the @transaction.atomic guarantee
        holds for a genuinely partial failure mid-loop.
        """
        mock_adjust.side_effect = [None, ValidationError("Simulated insufficient stock.")]

        request = self._get_request_with_session()
        cart = UnifiedSessionCartService(request)
        cart.add_product(product_id=self.product_simple.id, quantity=1)
        cart.add_variant(variant_id=self.variant.id, quantity=1)

        orders_before = Order.objects.count()
        items_before = OrderItem.objects.count()

        with self.assertRaises(ValidationError):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_PICKUP,
                customer_phone='+254700111111',
                pickup_slot=self.pickup_slot,
            )

        self.assertEqual(Order.objects.count(), orders_before)
        self.assertEqual(OrderItem.objects.count(), items_before)


class PostCommitBehaviourTests(OnlineCheckoutTestDataMixin, TestCase):
    """
    transaction.on_commit() callbacks never fire inside a plain TestCase
    (the outer transaction is rolled back, never committed). Django's
    captureOnCommitCallbacks(execute=True) is the documented way to test
    this behaviour without needing a full TransactionTestCase.
    """

    def test_cart_is_flushed_after_successful_commit(self):
        """
        WHAT: Successful order creation
        EXPECT: cart.flush_entire_cart() actually runs after commit --
                a second cart read shows it empty
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with self.captureOnCommitCallbacks(execute=True):
            OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_PICKUP,
                customer_phone='+254700111111',
                pickup_slot=self.pickup_slot,
            )

        cart_after = UnifiedSessionCartService(request)
        self.assertTrue(cart_after.is_empty())

    @patch('orders.online_services.OnlineOrderService._trigger_order_placed_notifications')
    def test_notification_trigger_called_after_successful_commit(self, mock_trigger):
        """
        WHAT: Successful order creation
        EXPECT: the notification dispatcher is called exactly once with the
                new order's id, only after the transaction commits
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with self.captureOnCommitCallbacks(execute=True):
            order = OnlineOrderService.create_order(
                request=request, branch=self.branch, customer=self.customer,
                order_type=Order.OrderType.ONLINE_PICKUP,
                customer_phone='+254700111111',
                pickup_slot=self.pickup_slot,
            )

        mock_trigger.assert_called_once_with(str(order.id))

    def test_sms_failure_does_not_break_order_creation(self):
        """
        WHAT: notifications.tasks.send_order_placed_sms.delay() raises
              (simulating a Celery broker outage, e.g. Redis down --
              a failure mode already proven to occur in this exact
              environment earlier this session)
        EXPECT: The order still exists and is fully committed -- the
                broadened exception handling in the notification dispatcher
                swallows the failure rather than letting it propagate
        """
        request = self._get_request_with_session()
        self._build_cart_with_product(request)

        with patch(
            'notifications.tasks.send_order_placed_sms.delay',
            side_effect=Exception("Simulated broker connection failure"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                order = OnlineOrderService.create_order(
                    request=request, branch=self.branch, customer=self.customer,
                    order_type=Order.OrderType.ONLINE_PICKUP,
                    customer_phone='+254700111111',
                    pickup_slot=self.pickup_slot,
                )

        self.assertTrue(Order.objects.filter(id=order.id).exists())


class CartFlashSalePricingTests(OnlineCheckoutTestDataMixin, TestCase):
    """
    Regression coverage for the fix making UnifiedSessionCartService.add_variant
    charge the LIVE flash-sale price at add-time, not the static effective_price.
    Previously FlashSale only affected storefront display, never the amount
    actually stored in the session cart / eventually charged.
    """
    def test_cart_uses_flash_sale_price_when_active(self):
        FlashSale.objects.create(
            variant=self.variant,
            sale_price=Decimal('350.00'),
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        request = self._get_request_with_session()
        cart = UnifiedSessionCartService(request)
        cart.add_variant(variant_id=self.variant.id, quantity=1)
        items = cart.get_cart_items_extended()
        self.assertEqual(items[0]['price'], Decimal('350.00'))
    def test_cart_uses_effective_price_when_no_active_flash_sale(self):
        request = self._get_request_with_session()
        cart = UnifiedSessionCartService(request)
        cart.add_variant(variant_id=self.variant.id, quantity=1)
        items = cart.get_cart_items_extended()
        self.assertEqual(items[0]['price'], self.variant.effective_price)
    def test_cart_ignores_expired_flash_sale(self):
        FlashSale.objects.create(
            variant=self.variant,
            sale_price=Decimal('200.00'),
            start_time=timezone.now() - timedelta(days=2),
            end_time=timezone.now() - timedelta(days=1),
            is_active=True,
        )
        request = self._get_request_with_session()
        cart = UnifiedSessionCartService(request)
        cart.add_variant(variant_id=self.variant.id, quantity=1)
        items = cart.get_cart_items_extended()
        self.assertEqual(items[0]['price'], self.variant.effective_price)
    def test_cart_ignores_inactive_flash_sale(self):
        """is_active=False must be excluded even if the time window is currently valid."""
        FlashSale.objects.create(
            variant=self.variant,
            sale_price=Decimal('100.00'),
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
            is_active=False,
        )
        request = self._get_request_with_session()
        cart = UnifiedSessionCartService(request)
        cart.add_variant(variant_id=self.variant.id, quantity=1)
        items = cart.get_cart_items_extended()
        self.assertEqual(items[0]['price'], self.variant.effective_price)
