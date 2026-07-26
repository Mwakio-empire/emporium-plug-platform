from django.template import context
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.contrib.auth import get_user_model
from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock
from orders.models import Order
from reports.models import OperationalAuditRiskLog, POSShift
from core.services import HighPerformanceOptimizationService


# Python 3.14 Compatibility Hotfix for Django Template Context Cloning
def patched_base_context_copy(self):
    """
    Safe replacement for Django's BaseContext.__copy__ to avoid super() 
    resolution errors under Python 3.14 execution layers.
    """
    cls = self.__class__
    duplicate = cls.__new__(cls)
    duplicate.__dict__.update(self.__dict__)
    if hasattr(self, 'dicts'):
        duplicate.dicts = self.dicts[:]
    return duplicate

# Apply runtime patch to Django's template engine context layers
context.BaseContext.__copy__ = patched_base_context_copy


# Properly resolve the enterprise custom user model
User = get_user_model()

class InternalCashDeskPOSCounterTerminalTestCase(TestCase):
    """
    Automated regression check matrix validating typeahead indexing filters,
    manager discount rule security checks, and session cart calculations.
    """
    def setUp(self):
        # 1. Topology Setup
        self.branch = Branch.objects.create(name="Mombasa Airport Road", location="Changamwe")
        User.objects.filter(username__in=["cashier_pos", "manager_pos"]).delete()

        # 2. RBAC Staff Accounts Setup with Explicit Unique Enterprise Emails
        self.cashier = User.objects.create_user(
            username="cashier_mwangi", 
            email="cashier.mwangi@retail.ke",
            phone_number="+254712345678",
            password="CashierSecurePass!2024", 
            role=User.Role.STAFF, 
            branch=self.branch
        )
        self.manager = User.objects.create_user(
            username="manager_nzomo", 
            email="manager.nzomo@retail.ke",
            phone_number="+254787654321",
            password="ManagerSecurePass!2024", 
            role=User.Role.BRANCH_MANAGER, 
            branch=self.branch
        )
        
        # 3. Catalog Configuration
        self.category = Category.objects.create(name="Home Furniture")
        self.product = Product.objects.create(
            name="Ortho Orthopedic Mattress", category=self.category, price=Decimal('28500.00'), sku="MAT-ORTHO-01"
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute_name="Dimensions", attribute_value="6x6 Super King"
        )
        
        # 4. Inventory Allocation
        self.stock_record = Stock.objects.create(
                    branch=self.branch, 
                    variant=self.variant,  # Assumes your inventory model uses a foreign key to ProductVariant
                    quantity=45
        )
        self.pos_shift = POSShift.objects.create(branch=self.branch, cashier=self.cashier)
    def test_pos_view_access_denied_for_unauthenticated_or_unauthorized_profiles(self):
        """Verifies that unauthorized or public user accounts are blocked from accessing internal cash registers."""
        # Unauthenticated check
        response = self.client.get(reverse('core:pos_workspace'))
        self.assertEqual(response.status_code, 302)  # Redirects straight into standard secure login prompt templates

    def test_asynchronous_pos_typeahead_lookup_filters_correctly(self):
            """Validates that search queries accurately match catalog items and return the correct HTML templates."""
            self.client.force_login(self.cashier)
            # Shifted parameter key from 'search' to 'q' to align with the active lookup view
            response = self.client.get(reverse('core:pos_product_lookup'), {'q': 'Mattress'})
            self.assertEqual(response.status_code, 200)
            # Adjusted target template string to match the active view destination
            self.assertTemplateUsed(response, 'core/partials/pos_search_results.html')
            self.assertContains(response, "Ortho Orthopedic Mattress")
            self.assertContains(response, "6x6 Super King")
    def test_pos_checkout_refusal_when_discount_lacks_manager_credentials(self):
            """Validates that trying to apply a discount without manager credentials triggers a fraud prevention block."""
            self.client.force_login(self.cashier)
            
            # Seed item variant directly into the cashier operational tray array
            self.client.post(reverse('core:pos_cart_action'), {'variant_id': self.variant.id, 'action': 'add'})
            
            # Submit order with an unapproved manual discount parameter
            response = self.client.post(reverse('core:pos_order_checkout'), {
                'customer_phone': '+254700000000',
                'discount_amount': '1500.00',
                'payment_method': 'CASH',
                'amount_received': '28500.00',
                'manager_username': ''  # Deliberately missing manager override parameters
            })
            
            # Explicitly pass status_code=403 to match the view's security response
            self.assertEqual(response.status_code, 403)
            self.assertContains(response, "Security Fault", status_code=403)

    def test_successful_pos_checkout_with_manager_clearance_override(self):
        """Validates that when a valid manager credentials parameter is sent, the walk-in transaction processes correctly."""
        self.client.force_login(self.cashier)
        
        # Seed item variant directly into the cashier operational tray array
        self.client.post(reverse('core:pos_cart_action'), {'variant_id': self.variant.id, 'action': 'add'})
        
        # Process checkout with a valid manager credentials verification loop
        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254799888777',
            'discount_amount': '500.00',
            'payment_method': 'CASH',
            'amount_received': '28000.00',
            'manager_username': self.manager.username,
            'manager_password': 'ManagerSecurePass!2024'  
            ,'discount_reason': 'Approved customer service discount'
        })
        self.assertEqual(response.status_code, 200)

    def test_cash_checkout_records_tender_and_change(self):
        self.client.force_login(self.cashier)
        self.client.post(
            reverse('core:pos_cart_action'),
            {'variant_id': self.variant.id, 'action': 'add'},
        )
        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254799888778',
            'discount_amount': '0.00',
            'payment_method': 'CASH',
            'amount_received': '30000.00',
        })
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(customer_phone='+254799888778')
        self.assertEqual(order.amount_received, Decimal('30000.00'))
        self.assertEqual(order.change_due, Decimal('1500.00'))

    def test_cash_checkout_rejects_insufficient_tender_atomically(self):
        self.client.force_login(self.cashier)
        self.client.post(
            reverse('core:pos_cart_action'),
            {'variant_id': self.variant.id, 'action': 'add'},
        )
        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254799888779',
            'discount_amount': '0.00',
            'payment_method': 'CASH',
            'amount_received': '28000.00',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.filter(customer_phone='+254799888779').exists())
        self.stock_record.refresh_from_db()
        self.assertEqual(self.stock_record.quantity, 45)

    def test_paybill_reference_alone_cannot_complete_sale(self):
        self.client.force_login(self.cashier)
        self.client.post(
            reverse('core:pos_cart_action'),
            {'variant_id': self.variant.id, 'action': 'add'},
        )
        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254799888780',
            'payment_method': 'PAYBILL',
            'payment_reference': 'TYPEDONLY1',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Order.objects.filter(customer_phone='+254799888780').exists())

    def test_verified_paybill_records_manager_audit_and_actual_cashier(self):
        self.client.force_login(self.cashier)
        self.client.post(
            reverse('core:pos_cart_action'),
            {'variant_id': self.variant.id, 'action': 'add'},
        )
        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254799888781',
            'payment_method': 'PAYBILL',
            'payment_reference': 'VERIFIEDPAY1',
            'manager_username': self.manager.username,
            'manager_password': 'ManagerSecurePass!2024',
            'payment_verification_reason': 'Matched amount and receipt in the authorized M-Pesa portal.',
        })
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(customer_phone='+254799888781')
        self.assertEqual(order.processed_by, self.cashier)
        self.assertTrue(OperationalAuditRiskLog.objects.filter(
            action_type='MANUAL_MPESA_MATCH',
            target_record_id=str(order.pk),
            initiator=self.manager,
        ).exists())
       
       # append to InternalCashDeskPOSCounterTerminalTestCase or a new class -- new class chosen
# to keep dashboard-permission tests isolated from the POS terminal suite.

class AnalyticsDashboardAccessTestCase(TestCase):

    def setUp(self):
        self.branch = Branch.objects.create(name="Dashboard Test Branch", location="Test")
        User.objects.filter(username__in=["dash_staff", "dash_manager"]).delete()
        self.staff = User.objects.create_user(
            username="dash_staff", email="dash.staff@test.ke",
            phone_number="+254711300001", password="DashPass123!",
            role=User.Role.STAFF, branch=self.branch,
        )
        self.manager = User.objects.create_user(
            username="dash_manager", email="dash.manager@test.ke",
            phone_number="+254711300002", password="DashPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )

    def test_manager_gets_200(self):
        """Regression: template_name pointed at nonexistent core/dashboard.html -- 500 before fix."""
        self.client.force_login(self.manager)
        response = self.client.get(reverse('core:analytics_dashboard'))
        self.assertEqual(response.status_code, 200)

def test_staff_gets_403(self):
        self.client.force_login(self.staff)
        client = self.client
        client.raise_request_exception = False
        response = client.get(reverse('core:analytics_dashboard'))
        self.assertEqual(response.status_code, 403)

class OptimizedProductCatalogDetailServiceTests(TestCase):
    """Regression coverage for core/services.py:get_optimized_product_catalog_details — zero prior coverage."""

    def setUp(self):
        self.category = Category.objects.create(name="Svc Test Category", slug="svc-test-category")
        self.product = Product.objects.create(
            name="Svc Test Product", slug="svc-test-product",
            category=self.category, price=Decimal("999.00"),
            status=Product.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute_name="Size", attribute_value="M",
        )

    def test_returns_none_for_nonexistent_product(self):
        result = HighPerformanceOptimizationService.get_optimized_product_catalog_details(999999)
        self.assertIsNone(result)

    def test_returns_product_and_variants_for_valid_id(self):
        result = HighPerformanceOptimizationService.get_optimized_product_catalog_details(self.product.id)
        self.assertIsNotNone(result)
        self.assertEqual(result['product'].id, self.product.id)
        self.assertEqual(len(result['variants']), 1)
        self.assertEqual(result['variants'][0].id, self.variant.id)

    def test_second_call_hits_cache(self):
        """Cache correctness: mutate DB after first call, confirm second call still returns stale (cached) data."""
        first = HighPerformanceOptimizationService.get_optimized_product_catalog_details(self.product.id)
        self.assertEqual(first['product'].name, "Svc Test Product")

        Product.objects.filter(id=self.product.id).update(name="Mutated After Cache")

        second = HighPerformanceOptimizationService.get_optimized_product_catalog_details(self.product.id)
        self.assertEqual(second['product'].name, "Svc Test Product")  # still stale
