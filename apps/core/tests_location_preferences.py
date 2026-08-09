from django.test import Client, TestCase
from django.urls import reverse

from logistics.models import KenyaCounty, KenyaTown


class ShopperLocationPreferenceTests(TestCase):
    def setUp(self):
        self.county = KenyaCounty.objects.get(code='37')
        self.county.is_active = True
        self.county.save(update_fields=['is_active'])
        self.town = KenyaTown.objects.filter(
            county=self.county,
            is_active=True,
        ).first()

    def test_listed_city_area_is_validated_and_saved_in_session(self):
        response = self.client.post(
            reverse('core:shopper_location'),
            {
                'county_code': self.county.code,
                'town_id': self.town.pk,
                'use_custom_town': 'false',
                'custom_town': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = self.client.session['shopper_location']
        self.assertEqual(saved['county_code'], self.county.code)
        self.assertEqual(saved['town_id'], self.town.pk)
        self.assertEqual(saved['town_name'], self.town.name.title())
        self.assertFalse(saved['use_custom_town'])
        self.assertContains(response, 'location_label')

    def test_cross_county_town_is_rejected_without_changing_session(self):
        other_county = KenyaCounty.objects.exclude(code=self.county.code).filter(
            is_active=True,
        ).first()
        other_town = KenyaTown.objects.filter(
            county=other_county,
            is_active=True,
        ).first()

        response = self.client.post(
            reverse('core:shopper_location'),
            {
                'county_code': self.county.code,
                'town_id': other_town.pk,
                'use_custom_town': 'false',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn('shopper_location', self.client.session)

    def test_unlisted_city_area_is_normalized_and_saved(self):
        response = self.client.post(
            reverse('core:shopper_location'),
            {
                'county_code': self.county.code,
                'town_id': '',
                'use_custom_town': 'true',
                'custom_town': '  Shinyalu   Market  ',
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = self.client.session['shopper_location']
        self.assertIsNone(saved['town_id'])
        self.assertEqual(saved['town_name'], 'Shinyalu Market')
        self.assertTrue(saved['use_custom_town'])

    def test_location_endpoint_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse('core:shopper_location'),
            {'county_code': self.county.code, 'town_id': self.town.pk},
        )

        self.assertEqual(response.status_code, 403)

    def test_storefront_renders_jumia_style_location_selector(self):
        session = self.client.session
        session['shopper_location'] = {
            'county_code': self.county.code,
            'county_name': self.county.name,
            'town_id': self.town.pk,
            'town_name': self.town.name,
            'use_custom_town': False,
        }
        session.save()

        response = self.client.get(reverse('core:storefront_home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose your location')
        self.assertContains(response, 'City / area')
        self.assertContains(response, 'data-shopper-location-open')
        self.assertContains(response, 'data-shopper-location-summary')
        self.assertContains(response, self.town.name.title())
        self.assertContains(response, '/static/core/location-selector.js')
