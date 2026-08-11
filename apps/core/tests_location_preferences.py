from django.test import TestCase
from django.urls import reverse


class StorefrontLocationPromptTests(TestCase):
    def test_storefront_does_not_ask_for_location_before_checkout(self):
        response = self.client.get(reverse('core:storefront_home'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Choose your location')
        self.assertNotContains(response, 'data-shopper-location-open')
        self.assertNotContains(response, 'data-shopper-location-summary')
        self.assertNotContains(response, 'location-selector.js')

    def test_removed_shopping_location_endpoint_returns_not_found(self):
        response = self.client.post('/shopping-location/', {})

        self.assertEqual(response.status_code, 404)
