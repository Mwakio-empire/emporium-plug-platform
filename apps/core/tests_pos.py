from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from orders.models import Order
from inventory.models import Stock
from reports.models import POSShift

User = get_user_model()

class PointOfSaleRealTimeTerminalTestSuite(TestCase):
    """
    Validates execution workflows for real-time terminal operations,
    asynchronous searches, and manager authorization checkpoints.
    """
    def setUp(self):
        self.branch = Branch.objects.create(name="Nairobi Terminal Node A", location="CBD", is_active=True)

        # Build strict role matrix contexts
        self.cashier = User.objects.create_user(
            username="cashier_jane",
            phone_number="0711111111",
            email="jane1@retail.co.ke",
            password="SecurePassword123",
            role=User.Role.STAFF,
            branch=self.branch
        )
        self.manager = User.objects.create_user(
            username="manager_boss",
            phone_number="0722222222",
            email="boss1@retail.co.ke",
            password="ManagerSecretKey456",
            role=User.Role.BRANCH_MANAGER,
            branch=self.branch
        )

        self.category = Category.objects.create(name="Computing Systems")
        self.product = Product.objects.create(
            name="ThinkPad Framework Laptop",
            category=self.category,
            price=Decimal("120000.00")
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            attribute_name="RAM",
            attribute_value="32GB",
            price_override=Decimal("125000.00")
        )
        self.stock_record = Stock.objects.create(
            branch=self.branch,
            variant=self.variant,
            quantity=100
        )
        self.pos_shift = POSShift.objects.create(branch=self.branch, cashier=self.cashier)

    def test_asynchronous_product_autocomplete_lookup_success(self):
        """Checks that search queries return matching product variant elements."""
        self.client.login(username="cashier_jane", password="SecurePassword123")
        response = self.client.get(reverse('core:pos_product_lookup'), {'q': 'ThinkPad'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ThinkPad Framework Laptop")
        self.assertContains(response, "KES 125000.00")


    def test_reactive_pos_cart_tray_state_mutation_sequence(self):
        """Verifies items add cleanly to the cashier's checkout tray."""
        self.client.login(username="cashier_jane", password="SecurePassword123")
        response = self.client.post(reverse('core:pos_cart_action'), {
            'variant_id': self.variant.id,
            'action': 'add'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ThinkPad Framework Laptop")
        # Template renders quantity as a bare span, not an "N items" string --
        # asserting on the actual quantity-display markup instead.
        self.assertContains(
            response,
            '<span class="text-xs font-bold px-2 text-center min-w-[20px] font-mono">1</span>',
        )
        self.assertContains(response, "KES 125000.00")
    def test_checkout_fails_without_manager_clearance_keys_if_discount_applied(self):
        """Ensures non-manager cashiers are blocked from applying discounts without credentials."""
        self.client.login(username="cashier_jane", password="SecurePassword123")
        
        # Load item into session state container
        self.client.post(reverse('core:pos_cart_action'), {
            'variant_id': self.variant.id,
            'action': 'add'
        })

        # Submit checkout with an unauthorized discount
        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '0700000000',
            'payment_method': 'CASH',
            'amount_received': '120000.00',
            'discount_amount': '5000.00',
            'manager_override_username': '',
            'manager_override_password': ''
        })
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Bypass Failure: Invalid manager authorization credentials", status_code=403)

    def test_checkout_succeeds_with_valid_manager_credential_overrides(self):
        """Verifies discount validation succeeds when proper manager credentials are provided."""
        self.client.login(username="cashier_jane", password="SecurePassword123")
        
        self.client.post(reverse('core:pos_cart_action'), {
            'variant_id': self.variant.id,
            'action': 'add'
        })

        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '0700000000',
            'payment_method': 'CASH',
            'amount_received': '120000.00',
            'discount_amount': '5000.00',
            'manager_override_username': 'manager_boss',
            'manager_override_password': 'ManagerSecretKey456'
            ,'discount_reason': 'Approved promotional adjustment'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transaction complete.")
        self.assertEqual(Order.objects.filter(status=Order.Status.COMPLETED).count(), 1)
