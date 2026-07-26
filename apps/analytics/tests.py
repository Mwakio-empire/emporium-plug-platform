from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from branches.models import Branch
from orders.models import Order
from analytics.models import AuditLog
from analytics.services import BusinessIntelligenceService, AuditTrackingService

User = get_user_model()


class BusinessIntelligenceAndSecurityAuditingTestSuite(TestCase):

    def setUp(self):
        """Prepares standard testing fixtures representing multiple operational locations."""
  # Administrative and Customer Entities Setup
        # CustomUserManager.create_superuser/create_user require username + phone_number
        # positionally — email-only kwargs raised TypeError before this fix.
        self.super_user = User.objects.create_superuser(
            username="admin_analytics", phone_number="+254700000001",
            email="admin@retail.com", password="SecurePassword123"
        )
        self.customer_entity = User.objects.create_user(
            username="buyer_analytics", phone_number="+254700000002",
            email="buyer@test.com", password="SecurePassword123"
        )

        # Distinct Physical Locations Initialization
        self.branch_nairobi = Branch.objects.create(name="Nairobi Core Hub", location="Nairobi CBD")
        self.branch_mombasa = Branch.objects.create(name="Mombasa Coast Node", location="Nyali")

        # Order.processed_by is PROTECT/required (no null, no default) — omitting it
        # raised IntegrityError on insert. Reusing customer_entity as processed_by is
        # a test-isolation shortcut only; the FK does not enforce role.
        common = dict(
            customer=self.customer_entity,
            customer_phone="+254700000002",
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.customer_entity,
        )

        # Mock Historical Invoiced Transactions
        Order.objects.create(branch=self.branch_nairobi, total_payable=5000.00, status="COMPLETED", **common)
        Order.objects.create(branch=self.branch_nairobi, total_payable=3500.00, status="COMPLETED", **common)
        Order.objects.create(branch=self.branch_mombasa, total_payable=11000.00, status="COMPLETED", **common)

        # This order should be omitted from final financial revenue calculations due to status constraints
        Order.objects.create(branch=self.branch_mombasa, total_payable=95000.00, status="PENDING", **common)

    def test_audit_trail_logging_accuracy(self):
        """Verifies that high-privilege activities are cleanly recorded in the tracking history."""
        log_record = AuditTrackingService.log_action(
            user=self.super_user,
            action_type=AuditLog.ActionTypes.IMPERSONATION_START,
            description="Super Admin started an impersonation session on account: buyer@test.com for debugging.",
            ip_address="192.168.100.45"
        )

        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(log_record.action_type, AuditLog.ActionTypes.IMPERSONATION_START)
        self.assertEqual(log_record.ip_address, "192.168.100.45")

    def test_consolidated_bi_metrics_computation(self):
        """Validates that multi-branch calculations aggregate correctly and ignore non-completed orders."""
        metrics = BusinessIntelligenceService.get_consolidated_dashboard_metrics()

        # Target Completed Aggregation: 5000 + 3500 + 11000 = 19,500.00
        self.assertEqual(float(metrics["total_revenue"]), 19500.00)
        self.assertEqual(metrics["total_orders"], 3)

        # Break down assertions by specific branch metrics
        performance_map = {item["name"]: float(item["branch_revenue"] or 0) for item in metrics["branch_performance"]}
        self.assertEqual(performance_map["Nairobi Core Hub"], 8500.00)
        self.assertEqual(performance_map["Mombasa Coast Node"], 11000.00)

    def test_audit_records_cannot_be_changed_or_deleted(self):
        record = AuditTrackingService.log_action(
            user=self.super_user,
            action_type=AuditLog.ActionTypes.LOGIN,
            description='Authenticated session created.',
        )
        record.description = 'Changed after creation'
        with self.assertRaises(ValidationError):
            record.save()
        with self.assertRaises(ValidationError):
            record.delete()
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=record.pk).update(description='Changed')
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=record.pk).delete()

    def test_user_with_audit_history_is_protected_from_deletion(self):
        AuditTrackingService.log_action(
            user=self.customer_entity,
            action_type=AuditLog.ActionTypes.LOGIN,
            description='Authenticated session created.',
        )
        with self.assertRaises(ProtectedError):
            self.customer_entity.delete()
