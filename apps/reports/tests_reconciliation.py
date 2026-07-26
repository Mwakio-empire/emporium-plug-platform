# apps/reports/tests_reconciliation.py
#
# Django's built-in test runner (TestCase, unittest-style), mirrors the
# pattern in orders/tests_pos_void.py and core/tests_pos_discount_audit.py.
#
# close_shift() fires its variance alert via transaction.on_commit --
# tests that need to observe it use captureOnCommitCallbacks(execute=True).
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.contrib.auth import get_user_model
from branches.models import Branch
from catalog.models import Category, Product
from orders.models import Order
from reports.models import POSShift, ShiftReconciliation
from reports.reconciliation_services import (
    ShiftReconciliationService, CASH_VARIANCE_ALERT_THRESHOLD,
)
User = get_user_model()


class ShiftReconciliationTestDataMixin:
    def setUp(self):
        cache.clear()  # clear any cached shift summary data from other tests
        self.branch = Branch.objects.create(name="Recon Test Branch", location="Test")
        self.other_branch = Branch.objects.create(name="Recon Other Branch", location="Elsewhere")
        self.cashier = User.objects.create_user(
            username="recon_cashier", phone_number="+254733700001",
            email="recon.cashier@test.ke", password="CashierPass123!",
            role=User.Role.STAFF, branch=self.branch,
        )
# STAFF role requires a branch (enforced in User.clean()) -- CUSTOMER
        # is the only role usable here to exercise close_shift()'s own
        # "cashier.branch is None" guard without tripping model validation
        # before the service is ever called.
        self.unassigned_cashier = User.objects.create_user(
            username="recon_cashier_noa", phone_number="+254733700002",
            email="recon.cashier.noa@test.ke", password="CashierPass123!",
            role=User.Role.CUSTOMER,
        )
        self.manager_same_branch = User.objects.create_user(
            username="recon_manager", phone_number="+254733700003",
            email="recon.manager@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.manager_other_branch = User.objects.create_user(
            username="recon_manager_other", phone_number="+254733700004",
            email="recon.manager.other@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.other_branch,
        )
        self.super_admin = User.objects.create_user(
            username="recon_superadmin", phone_number="+254733700005",
            email="recon.superadmin@test.ke", password="SuperAdminPass123!",
            role=User.Role.SUPER_ADMIN, is_staff=True, is_superuser=True,
        )
        self.category = Category.objects.create(name="Recon Category", slug="recon-category")
        self.product = Product.objects.create(
            name="Recon Product", slug="recon-product",
            category=self.category, price=Decimal("1000.00"),
            status=Product.Status.ACTIVE,
        )
        self.shift = POSShift.objects.create(branch=self.branch, cashier=self.cashier)

    def _cash_sale(self, amount, processed_by=None):
        sale_cashier = processed_by or self.cashier
        return Order.objects.create(
            branch=self.branch,
            order_type=Order.OrderType.WALK_IN,
            customer_phone="+254700111111",
            payment_method=Order.PaymentMethod.CASH,
            status=Order.Status.COMPLETED,
            processed_by=sale_cashier,
            pos_shift=self.shift if sale_cashier == self.cashier else None,
            subtotal=amount, total_payable=amount,
        )

    def _paybill_sale(self, amount):
        return Order.objects.create(
            branch=self.branch,
            order_type=Order.OrderType.WALK_IN,
            customer_phone="+254700111111",
            payment_method=Order.PaymentMethod.PAYBILL,
            status=Order.Status.COMPLETED,
            processed_by=self.cashier,
            pos_shift=self.shift,
            subtotal=amount, total_payable=amount,
        )


class CloseShiftExpectedCashTests(ShiftReconciliationTestDataMixin, TestCase):
    def test_expected_cash_derived_from_todays_cash_sales_only(self):
        """
        WHAT: Two CASH sales (3000 total) + one PAYBILL sale (5000) for
              the same cashier today
        EXPECT: expected_cash == 3000.00 -- PAYBILL revenue is excluded,
                matching what ShiftReportService reports as 'cash'
        """
        self._cash_sale(Decimal('2000.00'))
        self._cash_sale(Decimal('1000.00'))
        self._paybill_sale(Decimal('5000.00'))
        rec = ShiftReconciliationService.close_shift(
            cashier=self.cashier, actual_cash=Decimal('3000.00'),
        )
        self.assertEqual(rec.expected_cash, Decimal('3000.00'))
        self.assertEqual(rec.mpesa_total_settled, Decimal('5000.00'))

    def test_no_sales_today_expected_cash_is_zero(self):
        rec = ShiftReconciliationService.close_shift(
            cashier=self.cashier, actual_cash=Decimal('0.00'),
        )
        self.assertEqual(rec.expected_cash, Decimal('0.00'))
        self.assertEqual(rec.cash_variance, Decimal('0.00'))

    def test_other_cashiers_sales_not_counted(self):
        """WHAT: A sale processed by a DIFFERENT cashier at the same branch
        EXPECT: Not included in this cashier's expected_cash"""
        other_cashier = User.objects.create_user(
            username="recon_cashier_b", phone_number="+254733700006",
            email="recon.cashier.b@test.ke", password="CashierPass123!",
            role=User.Role.STAFF, branch=self.branch,
        )
        self._cash_sale(Decimal('4000.00'), processed_by=other_cashier)
        self._cash_sale(Decimal('1500.00'), processed_by=self.cashier)
        rec = ShiftReconciliationService.close_shift(
            cashier=self.cashier, actual_cash=Decimal('1500.00'),
        )
        self.assertEqual(rec.expected_cash, Decimal('1500.00'))


class CloseShiftVarianceTests(ShiftReconciliationTestDataMixin, TestCase):
    def test_exact_match_zero_variance(self):
        self._cash_sale(Decimal('1000.00'))
        rec = ShiftReconciliationService.close_shift(
            cashier=self.cashier, actual_cash=Decimal('1000.00'),
        )
        self.assertEqual(rec.cash_variance, Decimal('0.00'))

    def test_shortfall_produces_negative_variance(self):
        """WHAT: Counted less than expected
        EXPECT: cash_variance is negative (actual - expected)"""
        self._cash_sale(Decimal('1000.00'))
        rec = ShiftReconciliationService.close_shift(
            cashier=self.cashier, actual_cash=Decimal('900.00'),
        )
        self.assertEqual(rec.cash_variance, Decimal('-100.00'))

    def test_overage_produces_positive_variance(self):
        self._cash_sale(Decimal('1000.00'))
        rec = ShiftReconciliationService.close_shift(
            cashier=self.cashier, actual_cash=Decimal('1080.00'),
        )
        self.assertEqual(rec.cash_variance, Decimal('80.00'))

    def test_cashier_without_branch_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            ShiftReconciliationService.close_shift(
                cashier=self.unassigned_cashier, actual_cash=Decimal('0.00'),
            )
        self.assertIn("not assigned to a branch", str(ctx.exception))

    def test_negative_actual_cash_rejected(self):
        with self.assertRaises(ValidationError):
            ShiftReconciliationService.close_shift(
                cashier=self.cashier, actual_cash=Decimal('-50.00'),
            )

    def test_none_actual_cash_rejected(self):
        with self.assertRaises(ValidationError):
            ShiftReconciliationService.close_shift(
                cashier=self.cashier, actual_cash=None,
            )

    def test_reconciliation_persisted_with_correct_branch_and_cashier(self):
        self._cash_sale(Decimal('500.00'))
        rec = ShiftReconciliationService.close_shift(
            cashier=self.cashier, actual_cash=Decimal('500.00'), notes='All good.',
        )
        self.assertTrue(ShiftReconciliation.objects.filter(id=rec.id).exists())
        self.assertEqual(rec.branch, self.branch)
        self.assertEqual(rec.cashier, self.cashier)
        self.assertEqual(rec.notes, 'All good.')
        self.assertFalse(rec.is_verified_by_manager)


class CloseShiftAlertThresholdTests(ShiftReconciliationTestDataMixin, TestCase):
    @patch('notifications.tasks.send_shift_variance_alert.delay')
    def test_variance_within_threshold_does_not_alert(self, mock_alert):
        """WHAT: Variance of exactly the threshold (50.00)
        EXPECT: No alert -- strictly greater-than triggers, not >=."""
        self._cash_sale(Decimal('1000.00'))
        with self.captureOnCommitCallbacks(execute=True):
            ShiftReconciliationService.close_shift(
                cashier=self.cashier, actual_cash=Decimal('1050.00'),
            )
        mock_alert.assert_not_called()

    @patch('notifications.tasks.send_shift_variance_alert.delay')
    def test_variance_exceeding_threshold_alerts(self, mock_alert):
        self._cash_sale(Decimal('1000.00'))
        with self.captureOnCommitCallbacks(execute=True):
            rec = ShiftReconciliationService.close_shift(
                cashier=self.cashier, actual_cash=Decimal('900.00'),
            )
        mock_alert.assert_called_once_with(rec.id)

    @patch('notifications.tasks.send_shift_variance_alert.delay')
    def test_negative_variance_exceeding_threshold_alerts(self, mock_alert):
        """WHAT: A shortfall (negative variance) beyond threshold
        EXPECT: Alert still fires -- abs() applied to the threshold check"""
        self._cash_sale(Decimal('1000.00'))
        with self.captureOnCommitCallbacks(execute=True):
            rec = ShiftReconciliationService.close_shift(
                cashier=self.cashier, actual_cash=Decimal('800.00'),
            )
        mock_alert.assert_called_once_with(rec.id)

    @patch('notifications.tasks.send_shift_variance_alert.delay')
    def test_zero_variance_does_not_alert(self, mock_alert):
        self._cash_sale(Decimal('1000.00'))
        with self.captureOnCommitCallbacks(execute=True):
            ShiftReconciliationService.close_shift(
                cashier=self.cashier, actual_cash=Decimal('1000.00'),
            )
        mock_alert.assert_not_called()


class ShiftVarianceAlertTaskTests(ShiftReconciliationTestDataMixin, TestCase):
    @patch('notifications.tasks.send_sms_task.delay')
    def test_alert_notifies_same_branch_manager_and_super_admin_only(self, mock_sms):
        """
        WHAT: A flagged reconciliation at self.branch
        EXPECT: manager_same_branch and super_admin are notified;
                manager_other_branch is NOT
        """
        from notifications.tasks import send_shift_variance_alert
        self._cash_sale(Decimal('1000.00'))
        rec = ShiftReconciliation.objects.create(
            branch=self.branch, cashier=self.cashier,
            opened_at=self._cash_sale(Decimal('0.00')).created_at,
            expected_cash=Decimal('1000.00'), actual_cash=Decimal('800.00'),
        )
        send_shift_variance_alert(rec.id)
        notified_numbers = {call.args[0] for call in mock_sms.call_args_list}
        self.assertIn(str(self.manager_same_branch.phone_number), notified_numbers)
        self.assertIn(str(self.super_admin.phone_number), notified_numbers)
        self.assertNotIn(str(self.manager_other_branch.phone_number), notified_numbers)

    @patch('notifications.tasks.send_sms_task.delay')
    def test_alert_for_nonexistent_reconciliation_does_not_crash(self, mock_sms):
        from notifications.tasks import send_shift_variance_alert
        send_shift_variance_alert(999999)
        mock_sms.assert_not_called()


class VerifyReconciliationTests(ShiftReconciliationTestDataMixin, TestCase):
    def _flagged_reconciliation(self, branch=None):
        return ShiftReconciliation.objects.create(
            branch=branch or self.branch, cashier=self.cashier,
            opened_at=self._cash_sale(Decimal('0.00')).created_at,
            expected_cash=Decimal('1000.00'), actual_cash=Decimal('800.00'),
            requires_manager_review=True,
        )

    def test_staff_cannot_verify(self):
        rec = self._flagged_reconciliation()
        with self.assertRaises(ValidationError) as ctx:
            ShiftReconciliationService.verify_reconciliation(
                reconciliation_id=rec.id, manager=self.cashier, reason='Reviewed discrepancy details.',
            )
        self.assertIn("branch managers or super admins", str(ctx.exception))

    def test_customer_cannot_verify(self):
        customer = User.objects.create_user(
            username="recon_customer", phone_number="+254733700007",
            email="recon.customer@test.ke", password="CustPass123!",
            role=User.Role.CUSTOMER,
        )
        rec = self._flagged_reconciliation()
        with self.assertRaises(ValidationError):
            ShiftReconciliationService.verify_reconciliation(
                reconciliation_id=rec.id, manager=customer, reason='Reviewed discrepancy details.',
            )

    def test_manager_from_other_branch_rejected(self):
        rec = self._flagged_reconciliation(branch=self.branch)
        with self.assertRaises(ValidationError) as ctx:
            ShiftReconciliationService.verify_reconciliation(
                reconciliation_id=rec.id, manager=self.manager_other_branch, reason='Reviewed discrepancy details.',
            )
        self.assertIn("own branch", str(ctx.exception))
        rec.refresh_from_db()
        self.assertFalse(rec.is_verified_by_manager)

    def test_same_branch_manager_can_verify(self):
        rec = self._flagged_reconciliation()
        verified = ShiftReconciliationService.verify_reconciliation(
            reconciliation_id=rec.id, manager=self.manager_same_branch, reason='Count verified with cashier.',
        )
        self.assertTrue(verified.is_verified_by_manager)
        self.assertEqual(verified.verified_by, self.manager_same_branch)

    def test_super_admin_can_verify_any_branch(self):
        rec = self._flagged_reconciliation(branch=self.other_branch)
        verified = ShiftReconciliationService.verify_reconciliation(
            reconciliation_id=rec.id, manager=self.super_admin, reason='Count verified with cashier.',
        )
        self.assertTrue(verified.is_verified_by_manager)

    def test_already_verified_cannot_be_reverified(self):
        rec = self._flagged_reconciliation()
        ShiftReconciliationService.verify_reconciliation(
            reconciliation_id=rec.id, manager=self.manager_same_branch, reason='Count verified with cashier.',
        )
        with self.assertRaises(ValidationError) as ctx:
            ShiftReconciliationService.verify_reconciliation(
                reconciliation_id=rec.id, manager=self.super_admin, reason='Second verification attempt.',
            )
        self.assertIn("already been verified", str(ctx.exception))

    def test_nonexistent_reconciliation_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            ShiftReconciliationService.verify_reconciliation(
                reconciliation_id=999999, manager=self.manager_same_branch, reason='Reviewed missing record.',
            )
        self.assertIn("not found", str(ctx.exception))
