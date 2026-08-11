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

    def _add_cart_with_pickup(self):
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
        return branch

    def test_anonymous_customer_can_open_guest_checkout(self):
        response = self.client.get(reverse('checkout-page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex,nofollow">')
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

    def test_checkout_defaults_to_s18_pickup_and_offers_delivery_quote(self):
        self._add_cart_with_pickup()

        response = self.client.get(reverse('checkout-page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'S18 pickup')
        self.assertNotContains(response, 'value="ONLINE_DELIVERY"')
        self.assertContains(response, 'value="PICKUP" required checked')
        self.assertContains(response, 'value="DELIVERY_QUOTE"')
        self.assertContains(response, 'Send to my town')
        self.assertContains(response, 'No order or stock reservation yet')
        self.assertContains(response, 'id="delivery-quote-fields"')
        self.assertContains(response, '/static/orders/checkout.js')
        self.assertNotContains(response, 'aria-label="Order through WhatsApp"')
        self.assertContains(response, 'Need immediate help? Contact us on WhatsApp')

    def test_delivery_quote_uses_simple_typed_destination_fields(self):
        self._add_cart_with_pickup()

        response = self.client.get(reverse('checkout-page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<input id="quote-county"')
        self.assertContains(response, 'placeholder="Type your county"')
        self.assertNotContains(response, 'list="kenya-county-suggestions"')
        self.assertNotContains(response, '<datalist')
        self.assertContains(response, '<input id="quote-town"')
        self.assertContains(response, 'name="town" required disabled')
        self.assertContains(response, 'placeholder="Type your town or city"')
        self.assertContains(response, 'Preferred collection area or landmark')
        self.assertContains(response, 'Type the location in your own words.')
        self.assertNotContains(response, 'quote-town-retry')
        self.assertNotContains(response, 'data-towns-url')
        self.assertContains(response, 'value="PICKUP" required checked')

    def test_customer_name_help_is_accurate_for_pickup_and_delivery_quote(self):
        self._add_cart_with_pickup()

        response = self.client.get(reverse('checkout-page'))

        self.assertContains(response, 'aria-describedby="customer-name-help"')
        self.assertContains(
            response,
            'Optional for S18 pickup; required for a town delivery quote.',
        )

    def test_checkout_does_not_depend_on_a_saved_browsing_location(self):
        self._add_cart_with_pickup()
        response = self.client.get(reverse('checkout-page'))

        self.assertNotContains(response, 'data-saved-county')
        self.assertNotContains(response, 'data-saved-town-id')
        self.assertContains(response, 'Town or city')

    def test_tracking_page_is_a_data_free_shell(self):
        response = self.client.get(
            reverse('track-order', kwargs={'order_number': 'DNT-EXAMPLE1'}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Order DNT-EXAMPLE1')
        self.assertContains(response, '/static/orders/tracking.js')
