from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock
from orders.models import Order
from reports.models import POSShift, ShiftReconciliation
from reports.reconciliation_services import POSShiftService, ShiftReconciliationService


User = get_user_model()


class Phase6POSWorkflowTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Phase 6 Branch', location='Test')
        self.other_branch = Branch.objects.create(name='Other Phase 6 Branch', location='Elsewhere')
        self.cashier = User.objects.create_user(
            username='phase6_cashier', phone_number='+254711600001',
            email='phase6.cashier@test.invalid', password='CashierPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        self.manager = User.objects.create_user(
            username='phase6_manager', phone_number='+254711600002',
            email='phase6.manager@test.invalid', password='ManagerPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        category = Category.objects.create(name='Phase 6 Products')
        self.simple = Product.objects.create(
            name='Counter Soap', slug='counter-soap-phase6', sku='COUNTER-SOAP', category=category,
            price=Decimal('150.00'), status=Product.Status.ACTIVE,
        )
        self.variant_product = Product.objects.create(
            name='Counter Shirt', slug='counter-shirt-phase6', sku='COUNTER-SHIRT', category=category,
            price=Decimal('500.00'), status=Product.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            product=self.variant_product, attribute_name='Size', attribute_value='M',
        )
        self.other_product = Product.objects.create(
            name='Counter Other Branch Only', slug='counter-other-phase6', sku='COUNTER-OTHER', category=category,
            price=Decimal('99.00'), status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch, product=self.simple, quantity=4)
        Stock.objects.create(branch=self.branch, variant=self.variant, quantity=3)
        Stock.objects.create(branch=self.other_branch, product=self.other_product, quantity=9)
        self.client.force_login(self.cashier)

    def _open_shift(self, opening='0.00'):
        response = self.client.post(reverse('core:pos_shift_open'), {'opening_cash': opening})
        self.assertEqual(response.status_code, 200)
        return POSShift.objects.get(cashier=self.cashier, status=POSShift.Status.OPEN)

    def _add_simple(self):
        return self.client.post(reverse('core:pos_cart_action'), {
            'product_id': self.simple.pk,
            'action': 'add',
        })

    def test_sale_requires_open_shift_and_rolls_back(self):
        self._add_simple()
        response = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254711600010',
            'payment_method': Order.PaymentMethod.CASH,
            'amount_received': '150.00',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.filter(customer_phone='+254711600010').exists())
        self.assertEqual(Stock.objects.get(product=self.simple, branch=self.branch).quantity, 4)

    def test_open_shift_is_idempotent_and_unique(self):
        first = self._open_shift('200.00')
        second_response = self.client.post(
            reverse('core:pos_shift_open'), {'opening_cash': '999.00'},
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(POSShift.objects.filter(cashier=self.cashier).count(), 1)
        first.refresh_from_db()
        self.assertEqual(first.opening_cash, Decimal('200.00'))

    def test_simple_product_survives_cart_and_checkout(self):
        shift = self._open_shift()
        cart_response = self._add_simple()
        self.assertContains(cart_response, 'Counter Soap')
        self.assertContains(cart_response, 'KES 150.00')
        checkout = self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254711600011',
            'payment_method': Order.PaymentMethod.CASH,
            'amount_received': '200.00',
        })
        self.assertEqual(checkout.status_code, 200)
        order = Order.objects.get(customer_phone='+254711600011')
        self.assertEqual(order.pos_shift, shift)
        self.assertEqual(order.processed_by, self.cashier)
        self.assertEqual(order.items.get().product, self.simple)
        self.assertEqual(order.change_due, Decimal('50.00'))
        self.assertContains(checkout, reverse('order-receipt-pdf', args=[order.pk]))
        self.assertEqual(checkout['HX-Retarget'], '#pos-tray-wrapper')
        self.assertEqual(checkout['HX-Reswap'], 'innerHTML')
        self.assertFalse(self.client.session.get('dnt_pos_cart'))
        receipt = self.client.get(reverse('order-receipt-pdf', args=[order.pk]))
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt['Content-Type'], 'application/pdf')

    @patch('notifications.tasks.send_sms_task.delay')
    def test_cash_sms_receipt_contains_tender_change_and_payment_method(self, mock_sms):
        self._open_shift()
        self._add_simple()
        self.client.post(reverse('core:pos_order_checkout'), {
            'customer_phone': '+254711600013',
            'payment_method': Order.PaymentMethod.CASH,
            'amount_received': '200.00',
        })
        order = Order.objects.get(customer_phone='+254711600013')
        from notifications.tasks import send_walkin_receipt_sms
        send_walkin_receipt_sms(str(order.pk))
        message = mock_sms.call_args.args[1]
        self.assertIn('Payment: Cash Payment', message)
        self.assertIn('Cash: KES 200.00', message)
        self.assertIn('Change: KES 50.00', message)

    def test_lookup_is_branch_scoped_and_shows_availability(self):
        response = self.client.get(reverse('core:pos_product_lookup'), {'q': 'Counter'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Counter Soap')
        self.assertContains(response, '4 available')
        self.assertNotContains(response, 'Counter Other Branch Only')

    def test_customer_display_contains_amounts_but_no_customer_or_payment_secrets(self):
        self._add_simple()
        response = self.client.get(reverse('core:pos_customer_display_current'))
        self.assertContains(response, 'Counter Soap')
        self.assertContains(response, 'KES 150.00')
        self.assertNotContains(response, 'customer_phone')
        self.assertNotContains(response, 'payment_reference')
        display_page = self.client.get(reverse('core:pos_customer_display'))
        self.assertNotContains(display_page, self.cashier.username)
        self.assertNotContains(display_page, 'Logout')

    def test_shift_close_uses_opening_cash_and_only_its_orders(self):
        shift = self._open_shift('100.00')
        Order.objects.create(
            branch=self.branch, order_type=Order.OrderType.WALK_IN,
            customer_phone='+254711600012', payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier, pos_shift=shift,
            subtotal=Decimal('150.00'), total_payable=Decimal('150.00'),
            status=Order.Status.COMPLETED,
        )
        close_response = self.client.post(
            reverse('core:pos_shift_close'), {'actual_cash': '250.00'},
        )
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response['HX-Refresh'], 'true')
        reconciliation = ShiftReconciliation.objects.get(pos_shift=shift)
        self.assertEqual(reconciliation.expected_cash, Decimal('250.00'))
        self.assertFalse(reconciliation.requires_manager_review)
        shift.refresh_from_db()
        self.assertEqual(shift.status, POSShift.Status.CLOSED)
        with self.assertRaisesMessage(Exception, 'No open POS shift'):
            ShiftReconciliationService.close_shift(
                cashier=self.cashier,
                actual_cash=Decimal('250.00'),
            )

    def test_material_variance_requires_reasoned_manager_verification(self):
        shift, _ = POSShiftService.open_shift(cashier=self.cashier)
        reconciliation = ShiftReconciliationService.close_shift(
            cashier=self.cashier,
            actual_cash=Decimal('100.00'),
        )
        self.assertTrue(reconciliation.requires_manager_review)
        with self.assertRaisesMessage(Exception, 'at least 10 characters'):
            ShiftReconciliationService.verify_reconciliation(
                reconciliation_id=reconciliation.pk,
                manager=self.manager,
                reason='short',
            )
        verified = ShiftReconciliationService.verify_reconciliation(
            reconciliation_id=reconciliation.pk,
            manager=self.manager,
            reason='Cash count was repeated with the cashier and confirmed.',
        )
        self.assertTrue(verified.is_verified_by_manager)
        self.assertIsNotNone(verified.verified_at)
        self.assertEqual(ShiftReconciliation.objects.count(), 1)
