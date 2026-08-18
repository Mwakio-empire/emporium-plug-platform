from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from logistics.models import PickupSlot
from orders.models import Order


User = get_user_model()


class WhatsAppAssistedPickupTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Gaberone Plaza S18', location='Second floor, S18',
            offers_customer_pickup=True,
        )
        self.other_branch = Branch.objects.create(name='OTC', location='Third floor')
        self.staff = User.objects.create_user(
            username='whatsapp_staff', phone_number='+254711222333',
            email='wa.staff@example.com', password='SafePass!234',
            role=User.Role.STAFF, branch=self.branch,
        )
        category = Category.objects.create(name='Assisted', slug='assisted')
        self.product = Product.objects.create(
            name='Assisted item', slug='assisted-item', category=category,
            price=Decimal('750.00'), sku='WA-001',
        )
        self.stock = Stock.objects.create(branch=self.branch, product=self.product, quantity=3)
        self.slot = PickupSlot.objects.create(branch=self.branch, label='Today before 5 PM')
        self.client.force_login(self.staff)
        self.client.post(reverse('core:cart_action_gateway'), {
            'action': 'add', 'product_id': self.product.pk,
        })

    def test_staff_records_audited_cash_pickup_order(self):
        page = self.client.get(reverse('whatsapp-assisted-pickup'))
        key = page.context['idempotency_key']
        response = self.client.post(reverse('whatsapp-assisted-pickup'), {
            'idempotency_key': key,
            'customer_name': 'A Customer',
            'customer_phone': '0712 345 678',
            'customer_email': 'buyer@example.com',
            'pickup_slot_id': self.slot.pk,
            'notes': 'Customer confirmed one item in WhatsApp.',
            'confirmed': 'yes',
        })

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(sales_channel=Order.SalesChannel.WHATSAPP_ASSISTED)
        self.assertEqual(order.processed_by, self.staff)
        self.assertEqual(order.order_type, Order.OrderType.ONLINE_PICKUP)
        self.assertEqual(order.payment_method, Order.PaymentMethod.COD)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertContains(response, '#', status_code=201)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 1)

    def test_staff_cannot_create_for_another_branch(self):
        session = self.client.session
        session['dnt_storefront_cart_branch_id'] = self.other_branch.pk
        session.save()
        response = self.client.post(reverse('whatsapp-assisted-pickup'), {
            'idempotency_key': '1635f035-e7b7-454f-8660-4ae4492a7544',
            'customer_name': 'A Customer', 'customer_phone': '0712345678',
            'pickup_slot_id': self.slot.pk, 'confirmed': 'yes',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_customer_cannot_access_staff_intake(self):
        customer = User.objects.create_user(
            username='ordinary_customer', phone_number='+254711222334',
            email='customer-wa@example.com', password='SafePass!234',
        )
        self.client.force_login(customer)
        self.assertEqual(self.client.get(reverse('whatsapp-assisted-pickup')).status_code, 403)
