#
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
from orders.tasks import (
    send_pickup_reminders, auto_cancel_unresolved_pickups,
    PICKUP_REMINDER_HOURS,
)
User = get_user_model()
class PickupLifecycleTestDataMixin:
    def setUp(self):
        self.branch = Branch.objects.create(name="Pickup Lifecycle Branch", location="Test", offers_customer_pickup=True)
        self.customer = User.objects.create_user(
            username='pickuplifecyclecust0001', phone_number='+254788500001',
            email='pickuplifecyclecust0001@test.com', password='CustPass123!',
            role=User.Role.CUSTOMER,
        )
        self.manager = User.objects.create_user(
            username='pickuplifecyclemgr0001', phone_number='+254788500002',
            email='pickuplifecyclemgr0001@test.com', password='ManagerPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.category = Category.objects.create(name="Pickup Lifecycle Category", slug="pickup-lifecycle-category")
        self.product = Product.objects.create(
            name="Pickup Lifecycle Product", slug="pickup-lifecycle-product",
            category=self.category, price=Decimal("1000.00"), status=Product.Status.ACTIVE,
        )
        self.stock = Stock.objects.create(branch=self.branch, product=self.product, quantity=10)
    def _ready_for_pickup_order(self, ready_hours_ago, quantity=2, reminder_sent=False, expired=False):
        order = Order.objects.create(
            branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254700222333',
            payment_method=Order.PaymentMethod.MPESA_STK,
            status=Order.Status.READY_FOR_PICKUP,
            pickup_code='ABC123',
            processed_by=self.customer,
            subtotal=Decimal('2000.00'), total_payable=Decimal('2000.00'),
            pickup_expires_at=(
                timezone.now() - timedelta(hours=1)
                if expired else timezone.now() + timedelta(days=1)
            ),
        )
        OrderItem.objects.create(order=order, product=self.product, quantity=quantity, unit_price=Decimal('1000.00'))
        ready_time = timezone.now() - timedelta(hours=ready_hours_ago)
        history = OrderStatusHistory.objects.create(
            order=order, old_status=Order.Status.PROCESSING, new_status=Order.Status.READY_FOR_PICKUP,
            note='Marked ready.', changed_by=self.manager,
        )
        OrderStatusHistory.objects.filter(id=history.id).update(created_at=ready_time)
        if reminder_sent:
            order.pickup_reminder_sent_at = timezone.now()
            order.save(update_fields=['pickup_reminder_sent_at'])
        self.stock.reserved_quantity += quantity
        self.stock.save(update_fields=['reserved_quantity'])
        return order
class PickupReminderTaskTests(PickupLifecycleTestDataMixin, TestCase):
    @patch('notifications.tasks.send_pickup_reminder_sms.delay')
    def test_reminder_sent_after_threshold(self, mock_sms):
        order = self._ready_for_pickup_order(ready_hours_ago=PICKUP_REMINDER_HOURS + 1)
        send_pickup_reminders()
        order.refresh_from_db()
        self.assertIsNotNone(order.pickup_reminder_sent_at)
        mock_sms.assert_called_once_with(str(order.id))
    @patch('notifications.tasks.send_pickup_reminder_sms.delay')
    def test_no_reminder_before_threshold(self, mock_sms):
        order = self._ready_for_pickup_order(ready_hours_ago=1)
        send_pickup_reminders()
        order.refresh_from_db()
        self.assertIsNone(order.pickup_reminder_sent_at)
        mock_sms.assert_not_called()
    @patch('notifications.tasks.send_pickup_reminder_sms.delay')
    def test_reminder_not_resent(self, mock_sms):
        self._ready_for_pickup_order(ready_hours_ago=PICKUP_REMINDER_HOURS + 5, reminder_sent=True)
        send_pickup_reminders()
        mock_sms.assert_not_called()
    @patch('notifications.tasks.send_pickup_reminder_sms.delay')
    def test_non_ready_order_ignored(self, mock_sms):
        order = self._ready_for_pickup_order(ready_hours_ago=PICKUP_REMINDER_HOURS + 5)
        order.status = Order.Status.COLLECTED
        order.save(update_fields=['status'])
        send_pickup_reminders()
        mock_sms.assert_not_called()
class PickupAutoCancelTaskTests(PickupLifecycleTestDataMixin, TestCase):
    @patch('notifications.tasks.send_pickup_auto_cancel_manager_alert.delay')
    @patch('notifications.tasks.send_order_auto_cancelled_sms.delay')
    def test_cancels_and_restores_stock_after_collection_deadline(self, mock_customer_sms, mock_manager_alert):
        order = self._ready_for_pickup_order(ready_hours_ago=49, quantity=3, expired=True)
        stock_before = self.stock.quantity
        with self.captureOnCommitCallbacks(execute=True):
            auto_cancel_unresolved_pickups()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertIn('two-working-day', order.void_reason)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, stock_before)
        self.assertEqual(self.stock.reserved_quantity, 0)
        mock_customer_sms.assert_called_once_with(str(order.id))
        mock_manager_alert.assert_called_once_with(str(order.id))
    def test_not_cancelled_before_collection_deadline(self):
        order = self._ready_for_pickup_order(ready_hours_ago=10)
        auto_cancel_unresolved_pickups()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY_FOR_PICKUP)
    def test_collected_order_untouched(self):
        order = self._ready_for_pickup_order(ready_hours_ago=53, expired=True)
        order.status = Order.Status.COLLECTED
        order.save(update_fields=['status'])
        auto_cancel_unresolved_pickups()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COLLECTED)
    def test_status_history_entry_written(self):
        order = self._ready_for_pickup_order(ready_hours_ago=49, expired=True)
        auto_cancel_unresolved_pickups()
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=order, new_status=Order.Status.CANCELLED).count(), 1,
        )
    def test_one_failing_order_does_not_block_others(self):
        order_1 = self._ready_for_pickup_order(ready_hours_ago=49, expired=True)
        order_2 = self._ready_for_pickup_order(ready_hours_ago=50, expired=True)
        with patch('inventory.services.InventoryService.release_reservation') as mock_adjust:
            def side_effect(*args, **kwargs):
                if kwargs.get('reference_number') == order_1.order_number:
                    raise Exception("Simulated failure.")
                return None
            mock_adjust.side_effect = side_effect
            auto_cancel_unresolved_pickups()
        order_1.refresh_from_db()
        order_2.refresh_from_db()
        self.assertEqual(order_1.status, Order.Status.READY_FOR_PICKUP)
        self.assertEqual(order_2.status, Order.Status.CANCELLED)


    @patch('notifications.tasks.send_pickup_auto_cancel_manager_alert.delay')
    @patch('notifications.tasks.send_order_auto_cancelled_sms.delay')
    def test_guest_order_no_customer_does_not_crash(self, mock_customer_sms, mock_manager_alert):
        """
        Guest checkout (customer=None, phone-only per §1) must not crash
        StockAuditLog.triggered_by / OrderStatusHistory.changed_by --
        both required non-null FKs. Falls back to the system account.
        """
        from users.models import User, SYSTEM_ACCOUNT_USERNAME
        from inventory.models import StockAuditLog
        order = self._ready_for_pickup_order(ready_hours_ago=49, quantity=1, expired=True)
        order.customer = None
        order.save(update_fields=['customer'])
        with self.captureOnCommitCallbacks(execute=True):
            auto_cancel_unresolved_pickups()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        system_account = User.objects.get(username=SYSTEM_ACCOUNT_USERNAME)
        self.assertFalse(system_account.is_active)
        audit_entry = StockAuditLog.objects.get(
            reference_number=order.order_number,
            reason=StockAuditLog.Reason.RESERVATION_RELEASE,
        )
        self.assertEqual(audit_entry.triggered_by, system_account)
        history_entry = OrderStatusHistory.objects.get(order=order, new_status=Order.Status.CANCELLED)
        self.assertEqual(history_entry.changed_by, system_account)
