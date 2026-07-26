import os
import subprocess
import sys

from django.test import SimpleTestCase


class DeployedMediaSettingsTests(SimpleTestCase):
    base_environment = {
        'DEBUG': 'False',
        'SECRET_KEY': 'staging-test-secret-' + ('x' * 64),
        'ALLOWED_HOSTS': 'staging.example.test',
        'DATABASE_URL': 'postgresql://user:pass@localhost:5432/example',
        'REDIS_URL': 'redis://localhost:6379/1',
        'SITE_BASE_URL': 'https://staging.example.test',
        'CSRF_TRUSTED_ORIGINS': 'https://staging.example.test',
        'CLOUDINARY_CLOUD_NAME': '',
        'CLOUDINARY_API_KEY': '',
        'CLOUDINARY_API_SECRET': '',
    }

    def import_settings(self, **overrides):
        environment = os.environ.copy()
        environment.update(self.base_environment)
        environment.update(overrides)
        return subprocess.run(
            [sys.executable, '-c', 'import config.settings'],
            cwd=os.getcwd(),
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_staging_can_explicitly_boot_with_ephemeral_media(self):
        result = self.import_settings(
            ENVIRONMENT='staging',
            STAGING_ALLOW_EPHEMERAL_MEDIA='True',
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_staging_without_cloudinary_or_escape_hatch_is_rejected(self):
        result = self.import_settings(
            ENVIRONMENT='staging',
            STAGING_ALLOW_EPHEMERAL_MEDIA='False',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires Cloudinary credentials', result.stderr)

    def test_production_cannot_enable_staging_escape_hatch(self):
        result = self.import_settings(
            ENVIRONMENT='production',
            STAGING_ALLOW_EPHEMERAL_MEDIA='True',
            PRIVACY_CONTROLLER_NAME='Production Controller Test',
            PRIVACY_CONTACT_EMAIL='privacy@example.test',
            PRIVACY_NOTICE_APPROVED='True',
            NOTIFICATION_PROVIDER='africastalking',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            'STAGING_ALLOW_EPHEMERAL_MEDIA is restricted to the staging environment',
            result.stderr,
        )
