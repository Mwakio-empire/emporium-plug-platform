
# apps/orders/tests/test_checkout_api.py
#
# Django's built-in test runner via APITestCase (these are DRF views).
# Placed in the existing orders/tests/ folder alongside
# test_online_checkout.py, following the same feature-scoped naming.
#
# Tests the API CONTRACT end to end -- request body in, HTTP status +
# response body out, and resulting DB state. Does not depend on internal
# variable names inside online_services.py, only its documented,
# already-tested behavior (18/18 passing in test_online_checkout.py).

from decimal import Decimal
import uuid
from unittest.mock import patch
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from logistics.models import (
    KenyaCounty, ParcelDestination, PickupSlot, DeliveryAssignment, RiderProfile,
)
from orders.models import Order
from payments.models import MpesaTransaction
from catalog.constants import STOREFRONT_SELECTED_BRANCH_KEY
from marketing.models import Coupon
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

User = get_user_model()


class CheckoutAPITestDataMixin:

    def setUp(self):
        self.idempotency_key = str(uuid.uuid4())
        self.client.credentials(HTTP_IDEMPOTENCY_KEY=self.idempotency_key)
        self.branch = Branch.objects.create(
            name="Checkout API Test Branch", location="Test", offers_customer_pickup=True,
        )
        session = self.client.session
        session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch.pk
        session.save()
        self.customer = User.objects.create_user(
            username='checkoutapicust0001',
            phone_number='+254744000001',
            email='checkoutapicust0001@test.com',
            first_name='API', last_name='Customer',
            password='ApiCheckoutPass123!',
            role=User.Role.CUSTOMER,
        )
        self.category = Category.objects.create(
            name="Checkout API Category", slug="checkout-api-category",
        )
        self.product = Product.objects.create(
            name="Checkout API Kettle", slug="checkout-api-kettle",
            category=self.category, price=Decimal("1200.00"),
            weight=Decimal('1.00'),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch, product=self.product, quantity=15)

        self.county, _ = KenyaCounty.objects.get_or_create(code='37', defaults={'name': 'Kakamega'})
        self.parcel_destination = ParcelDestination.objects.create(
            county=self.county, town='Kakamega', collection_point='Main parcel stage',
            operator_name='Approved Test Operator', nairobi_dispatch_point='Nairobi stage',
            fee=Decimal('200.00'), included_weight_kg=Decimal('5.00'),
            additional_kg_fee=Decimal('30.00'), effective_from=timezone.localdate(),
            is_active=True,
        )
        self.pickup_slot = PickupSlot.objects.create(
            branch=self.branch, label="2:00 PM - 4:00 PM",
        )

    def _add_item_to_cart(self):
        """Adds an item via the real cart API so the session cart is populated."""
        self.client.post(
            reverse('cart:add'),
            data={'type': 'product', 'id': str(self.product.id), 'quantity': 2},
            format='json',
        )

    def _rotate_idempotency_key(self):
        self.idempotency_key = str(uuid.uuid4())
        self.client.credentials(HTTP_IDEMPOTENCY_KEY=self.idempotency_key)


class CheckoutInitViewTests(CheckoutAPITestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.customer)

    def test_guest_can_create_pickup_order(self):
        self.client.force_authenticate(user=None)
        self._rotate_idempotency_key()
        session = self.client.session
        session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch.pk
        session.save()
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '0712 345 678',
            'customer_email': 'guest@example.com',
            'pickup_slot_id': self.pickup_slot.id,
            'confirmed': True,
        }, format='json')

        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED, response.data,
        )
        self.assertIn('guest_access_token', response.data)
        order = Order.objects.get(order_number=response.data['order_number'])
        self.assertIsNone(order.customer)
        self.assertEqual(order.customer_phone, '+254712345678')
        self.assertEqual(order.customer_email, 'guest@example.com')
        self.assertTrue(order.guest_session_hash)
        self.assertEqual(order.processed_by.username, 'system_automation')
        self.assertFalse(order.processed_by.is_active)

    def test_missing_idempotency_key_rejected(self):
        self.client.credentials()
        response = self.client.post(reverse('checkout:init'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('idempotency', response.data['error'].lower())

    def test_staff_account_cannot_use_customer_checkout_api(self):
        staff = User.objects.create_user(
            username='checkoutstaff0001', phone_number='+254744000099',
            email='checkoutstaff0001@test.com', password='StaffPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        self.client.force_authenticate(user=staff)
        response = self.client.post(reverse('checkout:init'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_walk_in_order_type_rejected(self):
        """
        WHAT: order_type='WALK_IN' submitted to the customer-facing
              checkout API
        EXPECT: 400 -- WALK_IN must only ever come from the POS terminal
        """
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': 'WALK_IN',
            'customer_phone': '+254700111111',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('supports S18 pickup only', response.data['error'])

    def test_unknown_order_type_rejected(self):
        """WHAT: order_type='BOGUS'
        EXPECT: 400"""
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': 'BOGUS',
            'customer_phone': '+254700111111',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_payment_method_rejected(self):
        """
        WHAT: payment_method='PAYBILL' -- not allowed for online checkout
              (PAYBILL is walk-in-specific, verified this session)
        EXPECT: 400
        """
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': str(self.pickup_slot.id),
            'payment_method': 'PAYBILL',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('payment_method must be one of', response.data['error'])

    def test_invalid_branch_rejected(self):
        """
        WHAT: branch_id that doesn't exist
        EXPECT: 400
        NOTE: Branch.id is an integer AutoField, not UUID (confirmed by
        this test's own failure the first time it was written with a
        UUID-shaped fake id) -- using a large nonexistent integer instead.
        """
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': 999999999,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_parcel_checkout_is_rejected_even_with_unknown_destination(self):
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_DELIVERY,
            'customer_phone': '+254700111111',
            'customer_name': 'Parcel Recipient',
            'parcel_destination_id': str(uuid.uuid4()),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_parcel_checkout_is_rejected_even_with_active_destination(self):
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_DELIVERY,
            'customer_phone': '+254700111111',
            'customer_name': 'Parcel Recipient',
            'parcel_destination_id': str(self.parcel_destination.id),
            'confirmed': True,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('WhatsApp', response.data['error'])
        self.assertEqual(Order.objects.count(), 0)

    def test_successful_pickup_cod_order(self):
        """
        WHAT: Valid ONLINE_PICKUP + COD checkout
        EXPECT: 201, next_step='confirmed' (nothing left to pay online),
                order.status=PROCESSING (not PENDING -- COD never awaits
                an M-Pesa confirmation)
        """
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': str(self.pickup_slot.id),
            'payment_method': Order.PaymentMethod.COD,
            'confirmed': True,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['next_step'], 'confirmed')
        self.assertEqual(response.data['status'], Order.Status.PROCESSING)
        self.assertEqual(response.data['payment_method'], Order.PaymentMethod.COD)
        self.assertEqual(response.data['total_payable'], '2400.00')

    def test_same_idempotency_key_replays_one_order(self):
        self._add_item_to_cart()
        checkout_data = {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': self.pickup_slot.id,
            'confirmed': True,
        }
        first = self.client.post(reverse('checkout:init'), checkout_data, format='json')
        second = self.client.post(reverse('checkout:init'), checkout_data, format='json')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data['replayed'])
        self.assertEqual(first.data['order_number'], second.data['order_number'])
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 1)

    def test_same_idempotency_key_with_changed_details_is_conflict(self):
        self._add_item_to_cart()
        checkout_data = {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': self.pickup_slot.id,
            'confirmed': True,
        }
        first = self.client.post(reverse('checkout:init'), checkout_data, format='json')
        checkout_data['customer_phone'] = '+254700222222'
        second = self.client.post(reverse('checkout:init'), checkout_data, format='json')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)

    def test_expired_pickup_slot_rejected(self):
        from datetime import timedelta
        from django.utils import timezone

        self.pickup_slot.starts_at = timezone.now() - timedelta(hours=2)
        self.pickup_slot.ends_at = timezone.now() - timedelta(hours=1)
        self.pickup_slot.save()
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': self.pickup_slot.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_customer_email_rejected(self):
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'customer_email': 'not-an-email',
            'pickup_slot_id': self.pickup_slot.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_parcel_cod_is_rejected_before_payment_handling(self):
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_DELIVERY,
            'customer_phone': '+254700111111',
            'customer_name': 'Parcel Recipient',
            'parcel_destination_id': str(self.parcel_destination.id),
            'payment_method': Order.PaymentMethod.COD,
            'confirmed': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('WhatsApp', response.data['error'])
        self.assertEqual(Order.objects.count(), 0)

    def test_valid_order_requires_explicit_confirmation(self):
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': self.pickup_slot.id,
            'payment_method': Order.PaymentMethod.COD,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('agree to place', response.data['error'])
        self.assertEqual(Order.objects.count(), 0)


class CheckoutPreviewViewTests(CheckoutAPITestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.customer)
        self._add_item_to_cart()

    def test_preview_revalidates_simple_product_price_for_pickup(self):
        self.product.price = Decimal('1300.00')
        self.product.save(update_fields=['price'])

        response = self.client.post(reverse('checkout:preview'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'pickup_slot_id': self.pickup_slot.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['subtotal'], '2600.00')
        self.assertEqual(response.data['delivery_fee'], '0.00')
        self.assertEqual(response.data['total_payable'], '2600.00')
        self.assertEqual(len(response.data['price_changes']), 1)

    def test_coupon_preview_does_not_consume_coupon(self):
        coupon = Coupon.objects.create(
            code='SAVE100', discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('100.00'), active_from=timezone.now() - timedelta(hours=1),
            active_to=timezone.now() + timedelta(hours=1), usage_limit=1,
            min_order_value=Decimal('0.00'),
        )
        response = self.client.post(reverse('checkout:preview'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'pickup_slot_id': self.pickup_slot.id,
            'coupon_code': coupon.code,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['discount_amount'], '100.00')
        self.assertEqual(response.data['total_payable'], '2300.00')
        self.assertTrue(response.data['coupon_valid'])
        self.assertEqual(response.data['coupon_code'], 'SAVE100')
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 0)

    def test_invalid_coupon_preview_returns_plain_customer_feedback(self):
        response = self.client.post(reverse('checkout:preview'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'pickup_slot_id': self.pickup_slot.id,
            'coupon_code': 'NOT-A-COUPON',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['coupon_valid'])
        self.assertEqual(
            response.data['error'],
            'This coupon is inactive, expired, or invalid.',
        )

    def test_preview_reports_stock_change_without_creating_order(self):
        stock = Stock.objects.get(branch=self.branch, product=self.product)
        stock.quantity = 1
        stock.save(update_fields=['quantity'])

        response = self.client.post(reverse('checkout:preview'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'pickup_slot_id': self.pickup_slot.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Order.objects.count(), 0)


class CheckoutPaymentInitViewTests(CheckoutAPITestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.customer)
        self._add_item_to_cart()
        init_response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': str(self.pickup_slot.id),
            'confirmed': True,
        }, format='json')
        self.order_number = init_response.data['order_number']

    def test_missing_fields_rejected(self):
        """WHAT: POST /checkout/pay/ with no phone
        EXPECT: 400"""
        response = self.client.post(reverse('checkout:pay'), {
            'order_number': self.order_number,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_order_returns_404(self):
        """WHAT: order_number that doesn't exist
        EXPECT: 404"""
        response = self.client.post(reverse('checkout:pay'), {
            'order_number': 'DNT-NOTREAL1',
            'phone': '0712345678',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('orders.checkout_views.MpesaDarajaService.initiate_stk_push')
    def test_successful_stk_push(self, mock_stk):
        """
        WHAT: Valid PENDING order, STK push succeeds
        EXPECT: 200, checkout_request_id returned
        """
        mock_transaction = MpesaTransaction(
            checkout_request_id='ws_CO_TEST12345',
        )
        mock_stk.return_value = mock_transaction

        response = self.client.post(reverse('checkout:pay'), {
            'order_number': self.order_number,
            'phone': '0712345678',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['checkout_request_id'], 'ws_CO_TEST12345')

    @patch('orders.checkout_views.MpesaDarajaService.initiate_stk_push')
    def test_stk_push_failure_returns_fallback_instructions(self, mock_stk):
        """
        WHAT: Daraja unreachable -- initiate_stk_push raises ValidationError
        EXPECT: 503, fallback=True, manual payment instructions included
        """
        mock_stk.side_effect = ValidationError("Daraja gateway timeout.")

        response = self.client.post(reverse('checkout:pay'), {
            'order_number': self.order_number,
            'phone': '0712345678',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertTrue(response.data['fallback'])
        self.assertIn('Paybill', response.data['message'])


class CheckoutFallbackPaymentViewTests(CheckoutAPITestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.customer)
        self._add_item_to_cart()
        init_response = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': str(self.pickup_slot.id),
            'confirmed': True,
        }, format='json')
        self.order_number = init_response.data['order_number']

    def test_missing_fields_rejected(self):
        """WHAT: no mpesa_reference provided
        EXPECT: 400"""
        response = self.client.post(reverse('checkout:pay-fallback'), {
            'order_number': self.order_number,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_successful_fallback_submission(self):
        """
        WHAT: Customer submits a manual M-Pesa reference
        EXPECT: 200, reference stored separately from receipt evidence,
                order remains PENDING (manager must still verify)
        """
        response = self.client.post(reverse('checkout:pay-fallback'), {
            'order_number': self.order_number,
            'mpesa_reference': 'QGH7XY9999',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        order = Order.objects.get(order_number=self.order_number)
        self.assertEqual(order.status, Order.Status.PENDING)  # not auto-confirmed

        tx = MpesaTransaction.objects.get(order=order)
        self.assertIsNone(tx.confirmation_method)
        self.assertEqual(tx.submitted_reference, 'QGH7XY9999')
        self.assertIsNone(tx.mpesa_receipt_number)

    def test_duplicate_reference_rejected(self):
        """
        WHAT: Same mpesa_reference submitted for two different orders
        EXPECT: Second submission returns 400 -- idempotency protection
        """
        self.client.post(reverse('checkout:pay-fallback'), {
            'order_number': self.order_number,
            'mpesa_reference': 'QGH7XYDUPE1',
        }, format='json')

        self._add_item_to_cart()
        self._rotate_idempotency_key()
        second_init = self.client.post(reverse('checkout:init'), {
            'branch_id': str(self.branch.id),
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254700111111',
            'pickup_slot_id': str(self.pickup_slot.id),
            'confirmed': True,
        }, format='json')

        response = self.client.post(reverse('checkout:pay-fallback'), {
            'order_number': second_init.data['order_number'],
            'mpesa_reference': 'QGH7XYDUPE1',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GuestOrderAccessTests(CheckoutAPITestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self._add_item_to_cart()
        response = self.client.post(reverse('checkout:init'), {
            'branch_id': self.branch.id,
            'order_type': Order.OrderType.ONLINE_PICKUP,
            'customer_phone': '+254712345678',
            'pickup_slot_id': self.pickup_slot.id,
            'confirmed': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.order_number = response.data['order_number']
        self.token = response.data['guest_access_token']
        self.tracking_url = response.data['tracking_url']

    def test_guest_tracking_requires_valid_signed_token(self):
        url = reverse('orders:status', kwargs={'order_number': self.order_number})
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.get(url, {'token': f'{self.token}tampered'}).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        response = self.client.get(url, HTTP_X_GUEST_ORDER_TOKEN=self.token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['order_number'], self.order_number)
        self.assertIn(f'/orders/track/{self.order_number}/#', self.tracking_url)
        self.assertNotIn('?token=', self.tracking_url)

    @patch('orders.checkout_views.MpesaDarajaService.initiate_stk_push')
    def test_guest_can_initiate_payment_only_with_token(self, mock_stk):
        mock_stk.return_value = MpesaTransaction(checkout_request_id='guest-checkout-id')
        url = reverse('checkout:pay')
        without_token = self.client.post(url, {
            'order_number': self.order_number, 'phone': '+254712345678',
        }, format='json')
        self.assertEqual(without_token.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post(url, {
            'order_number': self.order_number,
            'phone': '+254712345678',
            'access_token': self.token,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class OrderStatusViewTests(CheckoutAPITestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.customer)
        order = Order.objects.create(
            branch=self.branch,
            customer=self.customer,
            processed_by=self.customer,
            order_type=Order.OrderType.ONLINE_DELIVERY,
            customer_phone='+254700111111',
            customer_name='Status Test Customer',
            payment_method=Order.PaymentMethod.MPESA_STK,
            status=Order.Status.PENDING,
            parcel_destination=self.parcel_destination,
            parcel_county_name=self.county.name,
            parcel_town=self.parcel_destination.town,
            parcel_collection_point=self.parcel_destination.collection_point,
            parcel_operator_name=self.parcel_destination.operator_name,
            subtotal=Decimal('2400.00'),
            delivery_fee=Decimal('200.00'),
            total_payable=Decimal('2600.00'),
        )
        self.order_number = order.order_number

    def test_nonexistent_order_returns_404(self):
        """WHAT: order_number that doesn't exist for this customer
        EXPECT: 404"""
        url = reverse('orders:status', kwargs={'order_number': 'DNT-NOTREAL1'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_customers_order_not_visible(self):
        """
        WHAT: A different customer tries to view this order
        EXPECT: 404 -- orders are scoped to their owner
        """
        other_customer = User.objects.create_user(
            username='otherapicust0001', phone_number='+254755000001',
            email='otherapicust0001@test.com', first_name='Other',
            last_name='Customer', password='OtherPass123!',
            role=User.Role.CUSTOMER,
        )
        self.client.force_authenticate(user=other_customer)
        url = reverse('orders:status', kwargs={'order_number': self.order_number})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_successful_status_retrieval_no_rider_yet(self):
        """
        WHAT: Order exists, no DeliveryAssignment created yet
        EXPECT: 200, rider is None entirely
        """
        url = reverse('orders:status', kwargs={'order_number': self.order_number})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['order_number'], self.order_number)
        self.assertIsNone(response.data['rider'])

    def test_rider_data_distinguishes_unassigned_from_assigned(self):
        """
        WHAT: A DeliveryAssignment exists but no rider has been picked
              yet (PENDING_ASSIGNMENT status, rider=None)
        EXPECT: rider is NOT None -- it shows the assignment status with
                name=None, distinct from "no assignment at all" (the
                fix from the last checkout_views.py review)
        """
        order = Order.objects.get(order_number=self.order_number)
        DeliveryAssignment.objects.create(order=order)  # rider defaults to None

        url = reverse('orders:status', kwargs={'order_number': self.order_number})
        response = self.client.get(url)

        self.assertIsNotNone(response.data['rider'])
        self.assertIsNone(response.data['rider']['name'])
        self.assertEqual(
            response.data['rider']['status'],
            DeliveryAssignment.DeliveryStatus.PENDING_ASSIGNMENT.label,
        )

    def test_rider_data_shows_name_when_assigned(self):
        """
        WHAT: A rider has actually been assigned
        EXPECT: rider.name is populated
        """
        rider_branch_staff = User.objects.create_user(
            username='riderapitest0001', phone_number='+254766000001',
            email='riderapitest0001@test.com', first_name='Fast',
            last_name='Rider', password='RiderPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        rider_profile = RiderProfile.objects.create(
            user=rider_branch_staff, branch=self.branch,
        )
        order = Order.objects.get(order_number=self.order_number)
        DeliveryAssignment.objects.create(
            order=order, rider=rider_profile,
            status=DeliveryAssignment.DeliveryStatus.ASSIGNED,
        )

        url = reverse('orders:status', kwargs={'order_number': self.order_number})
        response = self.client.get(url)

        self.assertEqual(response.data['rider']['name'], 'Fast Rider')
