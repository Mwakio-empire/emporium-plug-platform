import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.health import ASYNC_PIPELINE_HEARTBEAT_KEY
from core.tasks import record_async_pipeline_heartbeat


class HealthEndpointTests(TestCase):
    def test_liveness_has_no_dependency_details(self):
        response = self.client.get(reverse('core:health_live'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'alive'})
        self.assertEqual(response['Cache-Control'], 'no-store')
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
        self.assertEqual(response['Cache-Control'], 'no-store')

    @patch('core.health.cache.get', side_effect=RuntimeError('cache unavailable'))
    def test_readiness_returns_503_without_exception_details(self, _cache_get):
        response = self.client.get(reverse('core:health_ready'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable', 'failed': ['cache']})
        self.assertNotContains(response, 'RuntimeError', status_code=503)

    @patch('core.health.connection.cursor', side_effect=RuntimeError('database unavailable'))
    def test_readiness_returns_503_for_database_without_exception_details(self, _cursor):
        response = self.client.get(reverse('core:health_ready'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable', 'failed': ['database']})
        self.assertNotContains(response, 'RuntimeError', status_code=503)

    def test_operations_is_unavailable_before_async_pipeline_heartbeat(self):
        cache.delete(ASYNC_PIPELINE_HEARTBEAT_KEY)
        response = self.client.get(reverse('core:health_operations'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {'status': 'unavailable', 'failed': ['async_pipeline']},
        )

    def test_worker_executed_beat_heartbeat_makes_operations_healthy(self):
        recorded_at = record_async_pipeline_heartbeat()
        response = self.client.get(reverse('core:health_operations'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'operational'})
        self.assertEqual(float(cache.get(ASYNC_PIPELINE_HEARTBEAT_KEY)), recorded_at)

    def test_stale_async_pipeline_heartbeat_is_unavailable(self):
        cache.set(ASYNC_PIPELINE_HEARTBEAT_KEY, time.time() - 601, timeout=1200)
        response = self.client.get(reverse('core:health_operations'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {'status': 'unavailable', 'failed': ['async_pipeline']},
        )

    @patch(
        'core.health.cache.get',
        side_effect=['ok', RuntimeError('heartbeat cache read failed')],
    )
    def test_operations_heartbeat_cache_error_returns_503(self, _cache_get):
        response = self.client.get(reverse('core:health_operations'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable', 'failed': ['cache']})
        self.assertNotContains(response, 'RuntimeError', status_code=503)
