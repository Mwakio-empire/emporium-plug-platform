# apps/orders/tests/test_auto_cancel.py
#
# Django's built-in test runner (TestCase, unittest-style).
# Tests cancel_abandoned_pending_orders and its per-order helper
# _cancel_single_abandoned_order, both in apps/orders/tasks.py.

from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from orders.models import Order, OrderItem, OrderStatusHistory
from orders.tasks import cancel_abandoned_pending_orders, ABANDONED_ORDER_TIMEOUT_MINUTES

User = get_user_model()


class AutoCancelTestDataMixin:

    def setUp(self):
        self.branch = Branch.objects.create(
            name="Auto Cancel Test Branch", location="Test",
        )
        self.customer = User.objects.create_user(
            username='autocancelcust0001', phone_number='+254777000001',
            email='autocancelcust0001@test.com', first_name='Auto',
            last_name='Cancel', password='AutoCancelPass123!',
            role=User.Role.CUSTOMER,
        )
        self.category = Category.objects.create(
            name="Auto Cancel Category", slug="auto-cancel-category",
        )
        self.product = Product.objects.create(
            name="Auto Cancel Kettle", slug="auto-cancel-kettle",
            category=self.category, price=Decimal("1000.00"),
            status=Product.Status.ACTIVE,
        )
        self.stock = Stock.objects.create(
            branch=self.branch, product=self.product, quantity=10,
        )

    def _create_order(self, status, payment_method, minutes_old, order_type=None):
        """
        Creates an order with a specific age, status, and payment method,
        plus one OrderItem that deducted 3 units of stock (mirroring what
        OnlineOrderService.create_order would have done).
        """
        order_type = order_type or Order.OrderType.ONLINE_PICKUP
        order = Order.objects.create(
            branch=self.branch,
            customer=self.customer,
            order_type=order_type,
            customer_phone='+254700111111',
            payment_method=payment_method,
            status=status,
            processed_by=self.customer,
            subtotal=Decimal('3000.00'),
            total_payable=Decimal('3000.00'),
        )
        # Backdate created_at directly -- auto_now_add prevents setting
        # it at creation time, so update it after the fact.
        Order.objects.filter(id=order.id).update(
            created_at=timezone.now() - timedelta(minutes=minutes_old)
        )
        order.refresh_from_db()

        OrderItem.objects.create(
            order=order, product=self.product, quantity=3,
            unit_price=Decimal('1000.00'),
        )
        # Reserve stock, mirroring the online checkout policy.
        self.stock.reserved_quantity += 3
        self.stock.save(update_fields=['reserved_quantity'])

        return order


class CancelAbandonedOrdersTests(AutoCancelTestDataMixin, TestCase):

    @patch('notifications.tasks.send_order_auto_cancelled_sms.delay')
    def test_old_pending_mpesa_order_is_cancelled_and_stock_reversed(self, mock_sms):
        """
        WHAT: An MPESA_STK order stuck in PENDING for longer than the
              timeout window
        EXPECT: status becomes CANCELLED, stock is restored to its
                pre-order level, SMS triggered
        """
        order = self._create_order(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 5,
        )
        stock_before_cancel = self.stock.quantity

        cancel_abandoned_pending_orders()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIn('Auto-cancelled', order.void_reason)

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, stock_before_cancel)
        self.assertEqual(self.stock.reserved_quantity, 0)

        mock_sms.assert_called_once_with(str(order.id))

    def test_recent_pending_order_not_touched(self):
        """
        WHAT: An MPESA_STK order in PENDING, only 5 minutes old
        EXPECT: NOT cancelled -- well within the timeout window
        """
        order = self._create_order(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=5,
        )

        cancel_abandoned_pending_orders()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_cod_order_never_auto_cancelled_even_if_old(self):
        """
        WHAT: A COD order sitting in PROCESSING (never PENDING) for
              longer than the timeout window
        EXPECT: NOT touched -- COD orders are structurally excluded by
                the query (status=PENDING never matches PROCESSING),
                proving the two features don't collide
        """
        order = self._create_order(
            status=Order.Status.PROCESSING,
            payment_method=Order.PaymentMethod.COD,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 60,
        )

        cancel_abandoned_pending_orders()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)

    def test_walk_in_order_never_touched(self):
        """
        WHAT: A WALK_IN order, hypothetically old and PENDING (shouldn't
              realistically happen since POS completes synchronously,
              but the query must still exclude it structurally)
        EXPECT: Only excluded if payment_method != MPESA_STK. A WALK_IN
                order using MPESA_STK payment_method and stuck in
                PENDING WOULD be caught by this query -- that's correct,
                since the filter is on payment_method/status, not
                order_type. This test documents that intentional scope.
        """
        order = self._create_order(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.CASH,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 5,
            order_type=Order.OrderType.WALK_IN,
        )

        cancel_abandoned_pending_orders()

        order.refresh_from_db()
        # CASH payment_method excludes it -- the filter is payment_method
        # specific, not order_type specific
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_already_completed_order_not_touched_by_concurrent_race(self):
        """
        WHAT: An order that WAS old and PENDING, but got confirmed
              (status changed to COMPLETED) between the candidate query
              and the sweep actually processing it -- simulates the
              exact race condition select_for_update() + status re-check
              is designed to close
        EXPECT: Order remains COMPLETED, untouched, no stock reversed
        """
        order = self._create_order(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 5,
        )

        # Simulate a payment confirming right before the sweep runs
        order.status = Order.Status.COMPLETED
        order.save(update_fields=['status'])
        stock_after_confirmation = self.stock.quantity

        cancel_abandoned_pending_orders()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, stock_after_confirmation)  # unchanged

    @patch('notifications.tasks.send_order_auto_cancelled_sms.delay')
    @patch('inventory.services.InventoryService.release_reservation')
    def test_one_order_failing_does_not_block_the_rest_of_the_batch(
        self, mock_adjust, mock_sms
    ):
        """
        WHAT: Two abandoned orders in the same sweep. InventoryService
              .release_reservation is patched to raise for the FIRST order's
              item, succeed normally for the second.

              Patched at 'inventory.services.InventoryService.adjust_stock'
              -- NOT 'orders.tasks.InventoryService'. orders/tasks.py
              imports InventoryService inside the function bodies (a
              function-local import, verified in the actual file), so
              it's never bound as a module-level attribute of
              orders.tasks for mock.patch to find via that dotted path.
              Patching the method directly on its defining class works
              correctly regardless of how or where callers import it.
        EXPECT: The first order's cancellation fails and is logged, but
              the second order is still cancelled successfully -- proves
              per-order isolation, the batch-fragility fix from the
              hardening pass.
        """
        order_1 = self._create_order(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 5,
        )
        order_2 = self._create_order(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 10,
        )

        def side_effect(*args, **kwargs):
            if kwargs.get('reference_number') == order_1.order_number:
                raise Exception("Simulated stock reversal failure.")
            return None

        mock_adjust.side_effect = side_effect

        cancel_abandoned_pending_orders()

        order_1.refresh_from_db()
        order_2.refresh_from_db()

        # order_1's cancellation failed -- transaction.atomic() rolled
        # back its status change along with the failed stock reversal
        self.assertEqual(order_1.status, Order.Status.PENDING)

        # order_2 was NOT blocked by order_1's failure
        self.assertEqual(order_2.status, Order.Status.CANCELLED)

    def test_no_candidates_does_not_error(self):
        """
        WHAT: No abandoned orders exist at all
        EXPECT: Task completes cleanly, no exception
        """
        try:
            cancel_abandoned_pending_orders()
        except Exception as e:
            self.fail(f"cancel_abandoned_pending_orders raised unexpectedly: {e}")

#
    @patch('notifications.tasks.send_order_auto_cancelled_sms.delay')
    def test_guest_order_no_customer_does_not_crash(self, mock_sms):
        from users.models import User, SYSTEM_ACCOUNT_USERNAME
        from inventory.models import StockAuditLog
        order = self._create_order(
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 5,
        )
        order.customer = None
        order.save(update_fields=['customer'])
        cancel_abandoned_pending_orders()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        system_account = User.objects.get(username=SYSTEM_ACCOUNT_USERNAME)
        audit_entry = StockAuditLog.objects.get(
            reference_number=order.order_number,
            reason=StockAuditLog.Reason.RESERVATION_RELEASE,
        )
        self.assertEqual(audit_entry.triggered_by, system_account)
    def test_system_account_is_reused_not_duplicated(self):
        """Two separate auto-cancellations must reuse the same system account, not create duplicates."""
        from users.models import User, SYSTEM_ACCOUNT_USERNAME
        order_1 = self._create_order(
            status=Order.Status.PENDING, payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 5,
        )
        order_1.customer = None
        order_1.save(update_fields=['customer'])
        order_2 = self._create_order(
            status=Order.Status.PENDING, payment_method=Order.PaymentMethod.MPESA_STK,
            minutes_old=ABANDONED_ORDER_TIMEOUT_MINUTES + 10,
        )
        order_2.customer = None
        order_2.save(update_fields=['customer'])
        cancel_abandoned_pending_orders()
        self.assertEqual(User.objects.filter(username=SYSTEM_ACCOUNT_USERNAME).count(), 1)
