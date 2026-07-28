from pathlib import Path

from django.test import SimpleTestCase


class RenderStagingBlueprintTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.blueprint = (
            Path(__file__).resolve().parents[2] / 'render.staging.yaml'
        ).read_text(encoding='utf-8')

    def test_does_not_use_ignored_secret_placeholders_in_environment_group(self):
        self.assertNotIn('sync: false', self.blueprint)

    def test_uses_deterministic_https_staging_origin(self):
        hostname = 'emporium-plug-ke-staging-web.onrender.com'
        self.assertIn(f'value: {hostname}', self.blueprint)
        self.assertGreaterEqual(
            self.blueprint.count(f'value: https://{hostname}'),
            2,
        )

    def test_initial_deploy_configures_approved_branches(self):
        self.assertIn(
            'initialDeployHook: python manage.py configure_business_branches',
            self.blueprint,
        )

    def test_workers_wait_for_schema_and_key_value_is_persistent(self):
        self.assertEqual(
            self.blueprint.count('startCommand: python manage.py migrate --check'),
            2,
        )
        self.assertIn('persistenceMode: journal-snapshot', self.blueprint)

    def test_monitoring_uses_readiness_for_routing_and_async_heartbeat_for_operations(self):
        self.assertIn('healthCheckPath: /health/ready/', self.blueprint)
        self.assertNotIn('healthCheckPath: /health/operations/', self.blueprint)
        self.assertIn('ASYNC_HEARTBEAT_MAX_AGE_SECONDS', self.blueprint)

    def test_staging_external_integrations_are_safely_disabled(self):
        self.assertIn('value: console', self.blueprint)
        self.assertIn('value: "False"', self.blueprint)
        self.assertIn('STAGING_ALLOW_EPHEMERAL_MEDIA', self.blueprint)
