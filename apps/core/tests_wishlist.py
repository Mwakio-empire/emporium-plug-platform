from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, WishlistItem
from catalog.wishlist_services import WISHLIST_SESSION_KEY


User = get_user_model()


class WishlistJourneyTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Wishlist category', slug='wishlist-category')
        self.product = Product.objects.create(
            name='Saved product', slug='saved-product', category=category,
            price=Decimal('100.00'), sku='WISH-001',
        )

    def test_guest_can_toggle_and_view_wishlist_without_reserving_stock(self):
        response = self.client.post(
            reverse('core:wishlist_toggle', args=[self.product.pk]),
            {'next': reverse('core:wishlist')},
        )
        self.assertRedirects(response, reverse('core:wishlist'))
        self.assertEqual(self.client.session[WISHLIST_SESSION_KEY], [self.product.pk])
        self.assertContains(self.client.get(reverse('core:wishlist')), self.product.name)

    def test_guest_wishlist_survives_storefront_reload(self):
        self.client.post(
            reverse('core:wishlist_toggle', args=[self.product.pk]),
            {'next': reverse('core:storefront_home')},
        )

        first_reload = self.client.get(reverse('core:storefront_home'))
        second_reload = self.client.get(reverse('core:storefront_home'))

        self.assertContains(first_reload, f'Remove {self.product.name} from wishlist')
        self.assertContains(second_reload, f'Remove {self.product.name} from wishlist')
        self.assertEqual(self.client.session[WISHLIST_SESSION_KEY], [self.product.pk])

    def test_catalog_fragment_uses_full_storefront_as_wishlist_return_url(self):
        response = self.client.get(
            reverse('core:catalog_filter_engine'),
            {'search': self.product.name, 'sort': 'newest'},
        )

        self.assertContains(
            response,
            f'value="/?search={self.product.name.replace(" ", "+")}&amp;sort=newest#product-grid-target"',
            html=False,
        )

    def test_toggle_converts_fragment_redirect_into_full_storefront_redirect(self):
        fragment_url = f"{reverse('core:catalog_filter_engine')}?sort=newest"
        response = self.client.post(
            reverse('core:wishlist_toggle', args=[self.product.pk]),
            {'next': fragment_url},
        )

        self.assertRedirects(
            response,
            f"{reverse('core:storefront_home')}?sort=newest#product-grid-target",
        )

    def test_guest_wishlist_merges_on_customer_login(self):
        customer = User.objects.create_user(
            username='wishlist_customer', phone_number='+254711111122',
            email='wishlist@example.com', password='SafePass!234',
        )
        session = self.client.session
        session[WISHLIST_SESSION_KEY] = [self.product.pk]
        session.save()

        response = self.client.post(reverse('accounts:login'), {
            'identifier': customer.email,
            'password': 'SafePass!234',
            'next': reverse('core:wishlist'),
        })

        self.assertRedirects(response, reverse('core:wishlist'))
        self.assertTrue(WishlistItem.objects.filter(customer=customer, product=self.product).exists())
        self.assertNotIn(WISHLIST_SESSION_KEY, self.client.session)

    def test_toggle_rejects_external_redirect(self):
        response = self.client.post(
            reverse('core:wishlist_toggle', args=[self.product.pk]),
            {'next': 'https://attacker.example/steal'},
        )
        self.assertRedirects(response, reverse('core:storefront_home'))
