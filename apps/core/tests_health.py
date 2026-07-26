from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_liveness_has_no_dependency_details(self):
        response = self.client.get(reverse('core:health_live'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'alive'})
        self.assertRegex(response['X-Request-ID'], r'^[a-f0-9]{32}$')

    def test_safe_request_id_is_echoed_and_unsafe_value_is_replaced(self):
        accepted = self.client.get(
            reverse('core:health_live'), HTTP_X_REQUEST_ID='release-check-123',
        )
        rejected = self.client.get(
            reverse('core:health_live'), HTTP_X_REQUEST_ID='unsafe\nheader',
        )
        self.assertEqual(accepted['X-Request-ID'], 'release-check-123')
        self.assertNotEqual(rejected['X-Request-ID'], 'unsafe\nheader')

    def test_readiness_succeeds_when_dependencies_are_available(self):
        response = self.client.get(reverse('core:health_ready'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ready'})

    @patch('core.health.cache.get', side_effect=RuntimeError('cache unavailable'))
    def test_readiness_returns_503_without_exception_details(self, _cache_get):
        response = self.client.get(reverse('core:health_ready'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable', 'failed': ['cache']})
        self.assertNotContains(response, 'RuntimeError', status_code=503)
