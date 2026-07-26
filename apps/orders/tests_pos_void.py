# apps/orders/tests_pos_void.py
#
# Mirrors tests_pos_discount_audit.py's structure and fixture naming.
# Covers POSSalesService.void_sale() and the shared
# _authorize_manager_credentials() core it reuses from the discount flow.

from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock, StockAuditLog
from orders.models import Order, OrderItem, OrderStatusHistory
from orders.services import POSSalesService
from analytics.models import AuditLog
from reports.models import POSShift

User = get_user_model()


class POSVoidSaleTestCase(TestCase):

    def setUp(self):
        self.branch = Branch.objects.create(name="Void Test Branch", location="Test")
        self.other_branch = Branch.objects.create(name="Void Test Other Branch", location="Elsewhere")

        self.cashier = User.objects.create_user(
            username="void_cashier", phone_number="+254733500001",
            email="void.cashier@test.ke", password="CashierPass123!",
            role=User.Role.STAFF, branch=self.branch,
        )
        self.manager_same_branch = User.objects.create_user(
            username="void_manager", phone_number="+254733500002",
            email="void.manager@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.manager_other_branch = User.objects.create_user(
            username="void_manager_other", phone_number="+254733500003",
            email="void.manager.other@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.other_branch,
        )
        self.super_admin = User.objects.create_user(
            username="void_superadmin", phone_number="+254733500004",
            email="void.superadmin@test.ke", password="SuperAdminPass123!",
            role=User.Role.SUPER_ADMIN, is_staff=True, is_superuser=True,
        )

        self.category = Category.objects.create(name="Void Test Category")
        self.product = Product.objects.create(
            name="Void Test Product", category=self.category, price=Decimal("2000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute_name="Unit", attribute_value="Single",
        )
        # Post-sale stock baseline: sale of 3 units already deducted, 47 remain.
        self.stock = Stock.objects.create(branch=self.branch, variant=self.variant, quantity=47)

    def _create_completed_walk_in_order(self, quantity=3, order_type=Order.OrderType.WALK_IN,
                                          status=Order.Status.COMPLETED):
        order = Order.objects.create(
            branch=self.branch,
            order_type=order_type,
            customer_phone="+254700999888",
            subtotal=Decimal("6000.00"),
            total_payable=Decimal("6000.00"),
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier,
            status=status,
        )
        OrderItem.objects.create(
            order=order, variant=self.variant, quantity=quantity, unit_price=Decimal("2000.00"),
        )
        return order

    def _void(self, order_number, reason='Customer requested cancellation', manager_username='',
              manager_password='', requesting_staff=None):
        return POSSalesService.void_sale(
            order_number=order_number,
            branch=self.branch,
            requesting_staff=requesting_staff or self.cashier,
            manager_username=manager_username,
            manager_password=manager_password,
            void_reason=reason,
        )

    # --- Auth guard tests ---

    def test_missing_void_reason_rejected(self):
        order = self._create_completed_walk_in_order()
        with self.assertRaises(ValidationError) as ctx:
            self._void(order.order_number, reason='   ',
                       manager_username='void_manager', manager_password='ManagerPass123!')
        self.assertIn("void reason is mandatory", str(ctx.exception))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

    def test_invalid_credentials_denied_and_audited(self):
        order = self._create_completed_walk_in_order()
        with self.assertRaises(ValidationError):
            self._void(order.order_number, manager_username='void_manager', manager_password='WrongPass!')

        denied_log = AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.STOCK_VOID, description__icontains='DENIED',
        )
        self.assertEqual(denied_log.count(), 1)
        self.assertEqual(denied_log.first().user, self.cashier)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

    def test_branch_mismatched_manager_denied_and_audited(self):
        order = self._create_completed_walk_in_order()
        with self.assertRaises(ValidationError) as ctx:
            self._void(order.order_number, manager_username='void_manager_other', manager_password='ManagerPass123!')
        self.assertEqual(getattr(ctx.exception, 'code', None), 'branch_mismatch')

        denied_log = AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.STOCK_VOID, description__icontains='not registered to cashier branch',
        )
        self.assertEqual(denied_log.count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

    # --- Business rule guards ---

    def test_pending_order_rejected(self):
        order = self._create_completed_walk_in_order(status=Order.Status.PENDING)
        with self.assertRaises(ValidationError) as ctx:
            self._void(order.order_number, manager_username='void_manager', manager_password='ManagerPass123!')
        self.assertIn("Only COMPLETED sales", str(ctx.exception))

    def test_already_voided_order_rejected(self):
        order = self._create_completed_walk_in_order(status=Order.Status.VOIDED)
        with self.assertRaises(ValidationError):
            self._void(order.order_number, manager_username='void_manager', manager_password='ManagerPass123!')

    def test_online_order_rejected(self):
        order = self._create_completed_walk_in_order(order_type=Order.OrderType.ONLINE_PICKUP)
        with self.assertRaises(ValidationError) as ctx:
            self._void(order.order_number, manager_username='void_manager', manager_password='ManagerPass123!')
        self.assertIn("walk-in POS sales", str(ctx.exception))

    def test_nonexistent_order_rejected(self):
        with self.assertRaises(ValidationError):
            self._void('DNT-NOTREAL1', manager_username='void_manager', manager_password='ManagerPass123!')

    # --- Success paths ---

    @patch('notifications.tasks.send_void_processed_alert.delay')
    def test_same_branch_manager_granted_voids_and_restores_stock(self, mock_sms):
        order = self._create_completed_walk_in_order(quantity=3)
        stock_before = self.stock.quantity  # 47

        with self.captureOnCommitCallbacks(execute=True):
            voided_order = self._void(
                order.order_number, reason='Wrong item rung up',
                manager_username='void_manager', manager_password='ManagerPass123!',
            )

        voided_order.refresh_from_db()
        self.assertEqual(voided_order.status, Order.Status.VOIDED)
        self.assertEqual(voided_order.void_reason, 'Wrong item rung up')

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, stock_before + 3)  # restored

        self.assertTrue(
            StockAuditLog.objects.filter(
                reason=StockAuditLog.Reason.VOID_REVERSAL, reference_number=order.order_number,
            ).exists()
        )

        history = OrderStatusHistory.objects.filter(order=order, new_status=Order.Status.VOIDED)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().old_status, Order.Status.COMPLETED)

        granted_log = AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.STOCK_VOID, description__icontains='GRANTED',
        )
        self.assertEqual(granted_log.count(), 1)
        self.assertEqual(granted_log.first().user, self.manager_same_branch)

        mock_sms.assert_called_once_with(str(order.id), 'void_manager', 'Wrong item rung up')

    def test_super_admin_can_void_any_branch(self):
        order = self._create_completed_walk_in_order()
        voided_order = self._void(
            order.order_number, manager_username='void_superadmin', manager_password='SuperAdminPass123!',
        )
        self.assertEqual(voided_order.status, Order.Status.VOIDED)

    def test_voided_order_never_deleted(self):
        """Business Context §5: voided sales never disappear -- marked void with full trail."""
        order = self._create_completed_walk_in_order()
        self._void(order.order_number, manager_username='void_manager', manager_password='ManagerPass123!')
        self.assertTrue(Order.objects.filter(id=order.id).exists())
        self.assertEqual(Order.objects.get(id=order.id).status, Order.Status.VOIDED)

    def test_sale_from_closed_shift_requires_return_or_correction_workflow(self):
        order = self._create_completed_walk_in_order()
        shift = POSShift.objects.create(
            branch=self.branch,
            cashier=self.cashier,
            status=POSShift.Status.CLOSED,
        )
        order.pos_shift = shift
        order.save(update_fields=['pos_shift'])
        with self.assertRaises(ValidationError) as context:
            self._void(
                order.order_number,
                manager_username='void_manager',
                manager_password='ManagerPass123!',
            )
        self.assertIn('closed shift', str(context.exception))
