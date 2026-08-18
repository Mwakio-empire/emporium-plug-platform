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
        environment_group = self.blueprint.split('\nservices:', 1)[0]
        self.assertNotIn('sync: false', environment_group)

    def test_cloudinary_secret_is_required_by_every_process_service(self):
        self.assertEqual(self.blueprint.count('key: CLOUDINARY_URL'), 3)
        self.assertEqual(self.blueprint.count('sync: false'), 3)

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
        self.assertNotIn('STAGING_ALLOW_EPHEMERAL_MEDIA', self.blueprint)


class RenderProductionMediaBlueprintTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.blueprint = (
            Path(__file__).resolve().parents[2] / 'render.yaml'
        ).read_text(encoding='utf-8')

    def test_cloudinary_secret_is_not_placed_in_environment_group(self):
        environment_group = self.blueprint.split('\nservices:', 1)[0]
        self.assertNotIn('CLOUDINARY_', environment_group)

    def test_cloudinary_secret_is_required_by_every_process_service(self):
        self.assertEqual(self.blueprint.count('key: CLOUDINARY_URL'), 3)

    def test_production_uses_live_payment_mode_and_transactional_email(self):
        self.assertIn('key: MPESA_ENVIRONMENT\n        value: production', self.blueprint)
        self.assertNotIn('key: MPESA_ENVIRONMENT\n        value: sandbox', self.blueprint)
        self.assertIn('key: TRANSACTIONAL_EMAIL_ENABLED\n        value: "True"', self.blueprint)

    def test_production_requires_encrypted_off_site_backup_configuration(self):
        self.assertIn('key: BACKUP_ENABLED\n        value: "True"', self.blueprint)
        self.assertIn('key: BACKUP_S3_BUCKET', self.blueprint)
        self.assertIn('key: AWS_ACCESS_KEY_ID', self.blueprint)
        self.assertIn('key: AWS_SECRET_ACCESS_KEY', self.blueprint)
