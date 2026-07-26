# apps/orders/tests/test_document_services.py
#
# Covers the Phase 3 Item 5 fix: generate_invoice_pdf_stream crashed on
# variant-only OrderItems (item.product was None) and on guest orders
# (order.customer was None), and referenced the nonexistent
# Order.total_amount field.

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from orders.models import Order, OrderItem
from orders.document_services import CommercialDocumentGenerator

User = get_user_model()


class InvoicePDFGenerationTests(TestCase):

    def setUp(self):
        self.branch = Branch.objects.create(name="Invoice Test Branch", location="Test")
        self.staff = User.objects.create_user(
            username='invoicestaff0001', phone_number='+254788200001',
            email='invoicestaff0001@test.com', password='InvoicePass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        self.customer = User.objects.create_user(
            username='invoicecust0001', phone_number='+254788200002',
            email='invoicecust0001@test.com', first_name='Invoice',
            last_name='Customer', password='InvoicePass123!',
            role=User.Role.CUSTOMER,
        )
        self.category = Category.objects.create(name="Invoice Category", slug="invoice-category")
        self.product = Product.objects.create(
            name="Invoice Product", slug="invoice-product",
            category=self.category, price=Decimal("1000.00"),
            status=Product.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute_name="Size", attribute_value="Large",
        )

    def _base_order(self, customer, customer_name=''):
        return Order.objects.create(
            branch=self.branch, customer=customer, customer_name=customer_name,
            order_type=Order.OrderType.WALK_IN, customer_phone='+254700111111',
            payment_method=Order.PaymentMethod.CASH, status=Order.Status.COMPLETED,
            processed_by=self.staff, subtotal=Decimal('1000.00'),
            total_payable=Decimal('1000.00'),
        )

    def test_product_only_order_generates_valid_pdf(self):
        order = self._base_order(self.customer)
        OrderItem.objects.create(
            order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'),
        )
        buf = CommercialDocumentGenerator.generate_invoice_pdf_stream(order.id)
        self.assertTrue(buf.getvalue().startswith(b'%PDF'))

    def test_variant_only_order_does_not_crash(self):
        """Regression: item.product was None for variant items -- direct cause of the crash."""
        order = self._base_order(self.customer)
        OrderItem.objects.create(
            order=order, variant=self.variant, quantity=2, unit_price=Decimal('500.00'),
        )
        buf = CommercialDocumentGenerator.generate_invoice_pdf_stream(order.id)
        self.assertTrue(buf.getvalue().startswith(b'%PDF'))

    def test_guest_order_customer_none_does_not_crash(self):
        """Regression: order.customer.get_full_name() crashed when customer=None."""
        order = self._base_order(customer=None, customer_name='Walk-in Guest')
        OrderItem.objects.create(
            order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'),
        )
        buf = CommercialDocumentGenerator.generate_invoice_pdf_stream(order.id)
        self.assertTrue(buf.getvalue().startswith(b'%PDF'))

    def test_mixed_cart_order_does_not_crash(self):
        order = self._base_order(self.customer)
        OrderItem.objects.create(
            order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'),
        )
        OrderItem.objects.create(
            order=order, variant=self.variant, quantity=1, unit_price=Decimal('500.00'),
        )
        buf = CommercialDocumentGenerator.generate_invoice_pdf_stream(order.id)
        self.assertTrue(buf.getvalue().startswith(b'%PDF'))