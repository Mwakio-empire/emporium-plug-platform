from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from logistics.models import PickupSlot
from orders.cart_services import STOREFRONT_CART_BRANCH_KEY, STOREFRONT_CART_KEY


User = get_user_model()


class CheckoutPageTests(TestCase):

    def test_anonymous_customer_can_open_guest_checkout(self):
        response = self.client.get(reverse('checkout-page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review and confirm your order')
        self.assertContains(response, 'Add products to your cart before checking out.')
        self.assertContains(response, '/static/branding/favicon-cart.png')

    def test_authenticated_customer_can_open_checkout(self):
        user = User.objects.create_user(
            username='checkout-page-customer',
            phone_number='+254700999001',
            password='StrongCheckoutPass123!',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('checkout-page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review and confirm your order')

    def test_checkout_defaults_to_s18_pickup_and_routes_delivery_to_whatsapp(self):
        branch = Branch.objects.create(
            name='Checkout choice S18',
            location='Second floor, Gaberone Plaza',
            offers_customer_pickup=True,
        )
        category = Category.objects.create(
            name='Checkout choice category',
            slug='checkout-choice-category',
        )
        product = Product.objects.create(
            name='Checkout choice product',
            slug='checkout-choice-product',
            sku='CHK-CHOICE-1',
            category=category,
            price=Decimal('100.00'),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=branch, product=product, quantity=5)
        PickupSlot.objects.create(branch=branch, label='10:00 AM - 12:00 PM')
        session = self.client.session
        session[STOREFRONT_CART_KEY] = {
            f'p:{product.pk}': {
                'type': 'product',
                'product_id': str(product.pk),
                'quantity': 1,
                'price': '100.00',
                'name': product.name,
                'sku': product.sku,
            },
        }
        session[STOREFRONT_CART_BRANCH_KEY] = branch.pk
        session.save()

        response = self.client.get(reverse('checkout-page'))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'S18 pickup')
        self.assertNotContains(response, 'value="ONLINE_DELIVERY"')
        self.assertContains(response, 'value="ONLINE_PICKUP" required checked')
        self.assertContains(response, 'Send to my town')
        self.assertContains(response, 'Continue on WhatsApp')
        self.assertIn('Checkout%20choice%20product%20x1', html)
        self.assertIn('Subtotal%3A%20KES%20100.00', html)

    def test_tracking_page_is_a_data_free_shell(self):
        response = self.client.get(
            reverse('track-order', kwargs={'order_number': 'DNT-EXAMPLE1'}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Order DNT-EXAMPLE1')
        self.assertContains(response, '/static/orders/tracking.js')
