# apps/core/tests_pos_discount_audit.py
#
# Phase 4 Item 16: verifies POSSalesService.authorize_discount_override()
# consolidation. Covers the behavior WIDENING (SUPER_ADMIN now accepted for
# POS discount override, previously hard-rejected by the view) and verifies
# AuditLog entries are written for both denied and granted attempts.

from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock
from orders.models import Order
from analytics.models import AuditLog
from reports.models import POSShift

User = get_user_model()


class POSDiscountAuthorizationAuditTestCase(TestCase):

    def setUp(self):
        self.branch = Branch.objects.create(name="Discount Audit Branch", location="Test")
        self.other_branch = Branch.objects.create(name="Discount Audit Other Branch", location="Elsewhere")

        self.cashier = User.objects.create_user(
            username="discount_cashier", phone_number="+254733400001",
            email="discount.cashier@test.ke", password="CashierPass123!",
            role=User.Role.STAFF, branch=self.branch,
        )
        self.manager_same_branch = User.objects.create_user(
            username="discount_manager", phone_number="+254733400002",
            email="discount.manager@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.manager_other_branch = User.objects.create_user(
            username="discount_manager_other", phone_number="+254733400003",
            email="discount.manager.other@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.other_branch,
        )
        self.super_admin = User.objects.create_user(
            username="discount_superadmin", phone_number="+254733400004",
            email="discount.superadmin@test.ke", password="SuperAdminPass123!",
            role=User.Role.SUPER_ADMIN, is_staff=True, is_superuser=True,
        )

        self.category = Category.objects.create(name="Discount Audit Category")
        self.product = Product.objects.create(
            name="Discount Audit Product", category=self.category, price=Decimal("2000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute_name="Unit", attribute_value="Single",
        )
        Stock.objects.create(branch=self.branch, variant=self.variant, quantity=50)
        self.pos_shift = POSShift.objects.create(branch=self.branch, cashier=self.cashier)

    def _seed_cart_and_checkout(self, discount_amount, manager_username='', manager_password=''):
        self.client.force_login(self.cashier)
        self.client.post(reverse('core:pos_cart_action'), {
            'variant_id': self.variant.id, 'action': 'add',
        })
        return self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254700999888',
            'payment_method': 'CASH',
            'amount_received': '50000.00',
            'discount_amount': str(discount_amount),
            'manager_username': manager_username,
            'manager_password': manager_password,
            'discount_reason': 'Approved damaged packaging discount',
        })

    def test_invalid_credentials_denied_and_audited(self):
        response = self._seed_cart_and_checkout(
            discount_amount='200.00', manager_username='discount_manager', manager_password='WrongPassword!',
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Security Fault", status_code=403)

        denied_log = AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.DISCOUNT_APPLIED,
            description__icontains='DENIED',
        )
        self.assertEqual(denied_log.count(), 1)
        self.assertEqual(denied_log.first().user, self.cashier)

    def test_branch_mismatched_manager_denied_and_audited(self):
        response = self._seed_cart_and_checkout(
            discount_amount='200.00',
            manager_username='discount_manager_other', manager_password='ManagerPass123!',
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Bypass Failure", status_code=403)

        denied_log = AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.DISCOUNT_APPLIED,
            description__icontains='not registered to cashier branch',
        )
        self.assertEqual(denied_log.count(), 1)

    def test_same_branch_manager_granted_and_audited(self):
        response = self._seed_cart_and_checkout(
            discount_amount='200.00',
            manager_username='discount_manager', manager_password='ManagerPass123!',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(status=Order.Status.COMPLETED).count(), 1)

        granted_log = AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.DISCOUNT_APPLIED,
            description__icontains='GRANTED',
        )
        self.assertEqual(granted_log.count(), 1)
        self.assertEqual(granted_log.first().user, self.manager_same_branch)

    def test_super_admin_override_now_accepted_any_branch(self):
        """
        Behavior change from consolidation: the view previously rejected
        SUPER_ADMIN outright (role != BRANCH_MANAGER check). The service-level
        check always allowed SUPER_ADMIN. Consolidation resolves the
        disagreement in favor of the wider, already-established service rule.
        """
        response = self._seed_cart_and_checkout(
            discount_amount='200.00',
            manager_username='discount_superadmin', manager_password='SuperAdminPass123!',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(status=Order.Status.COMPLETED).count(), 1)
