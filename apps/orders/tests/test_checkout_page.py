from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from logistics.models import KenyaCounty, PickupSlot
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

    def test_checkout_defaults_to_s18_pickup_and_offers_structured_delivery_quote(self):
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

    def test_delivery_quote_uses_active_county_and_dependent_town_selects(self):
        self._add_cart_with_pickup()
        KenyaCounty.objects.filter(code='37').update(name='KAKAMEGA', is_active=True)
        KenyaCounty.objects.filter(code='38').update(name='VIHIGA', is_active=False)

        response = self.client.get(reverse('checkout-page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select id="quote-county"')
        self.assertContains(response, '<option value="37">Kakamega</option>')
        self.assertNotContains(response, 'Vihiga')
        self.assertContains(response, '<select id="quote-town"')
        self.assertContains(response, 'name="town_id" required disabled')
        self.assertContains(response, 'aria-describedby="quote-town-status"')
        self.assertContains(response, 'Select a county first')
        self.assertContains(response, 'id="quote-town-status"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(
            response,
            'id="quote-town-retry" type="button" hidden',
        )
        self.assertContains(response, 'Retry loading locations')
        self.assertContains(response, 'id="quote-custom-town-field" hidden')
        self.assertContains(response, 'id="quote-custom-town"')
        self.assertContains(response, "My city / area isn't listed")
        self.assertContains(response, 'data-towns-url="/api/logistics/towns/"')
        self.assertContains(response, 'value="PICKUP" required checked')

    def test_customer_name_help_is_accurate_for_pickup_and_delivery_quote(self):
        self._add_cart_with_pickup()

        response = self.client.get(reverse('checkout-page'))

        self.assertContains(response, 'aria-describedby="customer-name-help"')
        self.assertContains(
            response,
            'Optional for S18 pickup; required for a town delivery quote.',
        )

    def test_saved_shopping_location_is_available_to_prefill_delivery_quote(self):
        self._add_cart_with_pickup()
        county = KenyaCounty.objects.get(code='37')
        town = county.towns.filter(is_active=True).first()
        session = self.client.session
        session['shopper_location'] = {
            'county_code': county.code,
            'county_name': county.name,
            'town_id': town.pk,
            'town_name': town.name,
            'use_custom_town': False,
        }
        session.save()

        response = self.client.get(reverse('checkout-page'))

        self.assertContains(response, f'data-saved-county="{county.code}"')
        self.assertContains(response, f'data-saved-town-id="{town.pk}"')
        self.assertContains(response, 'City / area')

    def test_tracking_page_is_a_data_free_shell(self):
        response = self.client.get(
            reverse('track-order', kwargs={'order_number': 'DNT-EXAMPLE1'}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Order DNT-EXAMPLE1')
        self.assertContains(response, '/static/orders/tracking.js')
