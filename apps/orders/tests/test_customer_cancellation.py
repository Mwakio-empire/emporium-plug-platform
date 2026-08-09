from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock, StockAuditLog
from inventory.services import InventoryService
from orders.checkout_access import issue_guest_order_token
from orders.models import Order, OrderItem, OrderStatusHistory
from payments.models import MpesaTransaction
from payments.services import PaymentSettlementService


User = get_user_model()


class CustomerOrderCancellationTests(APITestCase):
    def setUp(self):
        self.system_actor = User.get_system_account()
        self.branch = Branch.objects.create(
            name='Cancellation Test S18', location='Test', offers_customer_pickup=True,
        )
        category = Category.objects.create(
            name='Cancellation products', slug='cancellation-products',
        )
        self.product = Product.objects.create(
            name='Cancellation kettle', slug='cancellation-kettle',
            category=category, price=Decimal('500.00'), status=Product.Status.ACTIVE,
        )
        self.stock = Stock.objects.create(
            branch=self.branch, product=self.product, quantity=8,
        )

    def _guest_order(self, *, payment_method=Order.PaymentMethod.MPESA_STK, status_value=None):
        status_value = status_value or (
            Order.Status.PROCESSING
            if payment_method == Order.PaymentMethod.COD
            else Order.Status.PENDING
        )
        order = Order.objects.create(
            branch=self.branch,
            processed_by=self.system_actor,
            customer_phone='+254712345678',
            order_type=Order.OrderType.ONLINE_PICKUP,
            payment_method=payment_method,
            status=status_value,
            subtotal=Decimal('500.00'),
            total_payable=Decimal('500.00'),
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=1,
            unit_price=Decimal('500.00'), total_price=Decimal('500.00'),
        )
        InventoryService.reserve_stock(
            branch=self.branch, product=self.product, quantity=1,
            triggered_by=self.system_actor, reference_number=order.order_number,
            note='Test order reservation.',
        )
        token = issue_guest_order_token(order)
        return order, token

    def _cancel(self, order, token, *, confirmed=True):
        return self.client.post(
            reverse('orders:cancel', kwargs={'order_number': order.order_number}),
            {'confirmed': confirmed}, format='json',
            HTTP_X_GUEST_ORDER_TOKEN=token,
        )

    def test_guest_can_cancel_unpaid_mpesa_order_and_release_stock_once(self):
        order, token = self._guest_order()

        response = self._cancel(order, token)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        order.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock.reserved_quantity, 0)
        self.assertEqual(
            StockAuditLog.objects.filter(
                reference_number=order.order_number,
                reason=StockAuditLog.Reason.RESERVATION_RELEASE,
            ).count(),
            1,
        )
        self.assertTrue(OrderStatusHistory.objects.filter(
            order=order, new_status=Order.Status.CANCELLED,
        ).exists())
        tracking = self.client.get(
            reverse('orders:status', kwargs={'order_number': order.order_number}),
            HTTP_X_GUEST_ORDER_TOKEN=token,
        )
        self.assertEqual(
            tracking.data['status_history'][-1]['message'],
            'You cancelled this order and its reserved items were released.',
        )

        duplicate = self._cancel(order, token)
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            StockAuditLog.objects.filter(
                reference_number=order.order_number,
                reason=StockAuditLog.Reason.RESERVATION_RELEASE,
            ).count(),
            1,
        )

    def test_guest_can_cancel_cash_at_pickup_order_in_grace_period(self):
        order, token = self._guest_order(payment_method=Order.PaymentMethod.COD)

        response = self._cancel(order, token)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_cancellation_requires_explicit_confirmation_and_valid_owner_token(self):
        order, token = self._guest_order()

        self.assertEqual(self._cancel(order, token, confirmed=False).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.post(
                reverse('orders:cancel', kwargs={'order_number': order.order_number}),
                {'confirmed': True}, format='json', HTTP_X_GUEST_ORDER_TOKEN=f'{token}tampered',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_order_cannot_be_self_cancelled_after_grace_period(self):
        order, token = self._guest_order()
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=11))

        response = self._cancel(order, token)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('window has ended', response.data['error'])
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 1)

    def test_payment_evidence_blocks_self_cancellation(self):
        order, token = self._guest_order()
        MpesaTransaction.objects.create(
            order=order, merchant_request_id='cancel-merchant-confirmed',
            checkout_request_id='cancel-checkout-confirmed',
            status=MpesaTransaction.Status.QUERY_CONFIRMED,
            expected_amount=order.total_payable,
        )

        response = self._cancel(order, token)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('being checked', response.data['error'])

    def test_late_successful_callback_after_cancellation_requires_reconciliation(self):
        order, token = self._guest_order()
        payment = MpesaTransaction.objects.create(
            order=order, merchant_request_id='cancel-late-merchant',
            checkout_request_id='cancel-late-checkout',
            status=MpesaTransaction.Status.PENDING,
            expected_amount=order.total_payable,
        )
        self.assertEqual(self._cancel(order, token).status_code, status.HTTP_200_OK)

        outcome = PaymentSettlementService.confirm(
            payment.pk, amount='500.00', receipt_number='CANCEL123ABC',
            raw_callback_payload={'result_code': 0},
        )

        self.assertEqual(outcome, 'reconciliation_required')
        payment.refresh_from_db()
        order.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(payment.status, MpesaTransaction.Status.RECONCILIATION_REQUIRED)
        self.assertEqual(payment.mpesa_receipt_number, 'CANCEL123ABC')
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock.quantity, 8)
        self.assertEqual(self.stock.reserved_quantity, 0)

    def test_status_api_exposes_cancellation_window_without_internal_reason(self):
        order, token = self._guest_order(payment_method=Order.PaymentMethod.COD)

        response = self.client.get(
            reverse('orders:status', kwargs={'order_number': order.order_number}),
            HTTP_X_GUEST_ORDER_TOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['can_cancel'])
        self.assertIsNotNone(response.data['cancellation_deadline'])
        self.assertNotIn('void_reason', response.data)
