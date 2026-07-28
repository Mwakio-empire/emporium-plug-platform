from unittest.mock import patch

from django.test import SimpleTestCase

from core.load_testing import RequestResult, run_capacity_probe, validate_target


class CapacityProbeTests(SimpleTestCase):
    def test_remote_target_is_rejected_without_exact_authorization(self):
        with self.assertRaisesMessage(ValueError, 'explicit authorization'):
            validate_target('https://staging.example.test', allow_remote=False, expected_host=None)
        with self.assertRaisesMessage(ValueError, 'exactly match'):
            validate_target(
                'https://staging.example.test',
                allow_remote=True,
                expected_host='production.example.test',
            )

    def test_embedded_credentials_are_rejected(self):
        with self.assertRaisesMessage(ValueError, 'must not be embedded'):
            validate_target('http://user:secret@localhost:8000', allow_remote=False, expected_host=None)

    @patch('core.load_testing._request_once')
    def test_summary_reports_failures_latency_and_statuses(self, request_once):
        request_once.side_effect = [
            RequestResult(10, 200, True),
            RequestResult(20, 200, True),
            RequestResult(30, 503, False),
            RequestResult(40, None, False),
        ]

        summary = run_capacity_probe(
            base_url='http://127.0.0.1:8000',
            paths=['/health/live/'],
            total_requests=4,
            concurrency=1,
            timeout_seconds=1,
        )

        self.assertEqual(summary['successes'], 2)
        self.assertEqual(summary['failures'], 2)
        self.assertEqual(summary['failure_rate'], 0.5)
        self.assertEqual(summary['latency_ms'], {'p50': 20, 'p95': 40, 'p99': 40})
        self.assertEqual(summary['status_counts'], {'200': 2, '503': 1, 'network_error': 1})

    def test_probe_limits_prevent_accidental_unbounded_load(self):
        with self.assertRaisesMessage(ValueError, 'between 1 and 10,000'):
            run_capacity_probe(
                base_url='http://localhost:8000',
                paths=['/'],
                total_requests=10_001,
                concurrency=1,
                timeout_seconds=1,
            )
