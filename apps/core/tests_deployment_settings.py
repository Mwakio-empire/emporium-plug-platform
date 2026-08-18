import os
import subprocess
import sys

import cloudinary
from django.conf import settings
from django.test import SimpleTestCase


class TestMediaIsolationTests(SimpleTestCase):
    def test_test_suite_uses_synthetic_cloudinary_identity_and_local_storage(self):
        self.assertEqual(cloudinary.config().cloud_name, 'test-cloud')
        self.assertEqual(
            settings.STORAGES['default']['BACKEND'],
            'django.core.files.storage.FileSystemStorage',
        )


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

    def import_settings(self, *, script='import config.settings', **overrides):
        environment = os.environ.copy()
        environment.update(self.base_environment)
        environment.update(overrides)
        return subprocess.run(
            [sys.executable, '-c', script],
            cwd=os.getcwd(),
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_staging_can_boot_with_cloudinary_url(self):
        result = self.import_settings(
            ENVIRONMENT='staging',
            CLOUDINARY_URL='cloudinary://key:secret@staging-cloud',
            PRIVACY_CONTROLLER_NAME='Staging synthetic data only',
            PRIVACY_CONTACT_EMAIL='staging-invalid@example.invalid',
            PRIVACY_NOTICE_APPROVED='False',
            NOTIFICATION_PROVIDER='console',
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_staging_uses_cloudinary_as_default_media_storage(self):
        result = self.import_settings(
            script=(
                'import config.settings as s; '
                'print(s.STORAGES["default"]["BACKEND"])'
            ),
            ENVIRONMENT='staging',
            CLOUDINARY_URL='cloudinary://key:secret@staging-cloud',
            PRIVACY_CONTROLLER_NAME='Staging synthetic data only',
            PRIVACY_CONTACT_EMAIL='staging-invalid@example.invalid',
            PRIVACY_NOTICE_APPROVED='False',
            NOTIFICATION_PROVIDER='console',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            'cloudinary_storage.storage.MediaCloudinaryStorage',
        )

    def test_staging_without_cloudinary_is_rejected(self):
        result = self.import_settings(
            ENVIRONMENT='staging',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires Cloudinary credentials', result.stderr)

    def test_production_without_cloudinary_is_rejected(self):
        result = self.import_settings(**self.production_environment(
            CLOUDINARY_URL='',
            CLOUDINARY_CLOUD_NAME='',
            CLOUDINARY_API_KEY='',
            CLOUDINARY_API_SECRET='',
        ))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires Cloudinary credentials', result.stderr)

    def production_environment(self, **overrides):
        values = {
            'ENVIRONMENT': 'production',
            'CLOUDINARY_URL': 'cloudinary://key:secret@production-cloud',
            'PRIVACY_CONTROLLER_NAME': 'Approved Controller',
            'PRIVACY_CONTACT_EMAIL': 'privacy@example.test',
            'PRIVACY_NOTICE_APPROVED': 'True',
            'NOTIFICATION_PROVIDER': 'africastalking',
            'AFRICASTALKING_USERNAME': 'emporium-test',
            'AFRICASTALKING_API_KEY': 'not-a-real-provider-key',
            'TRANSACTIONAL_EMAIL_ENABLED': 'True',
            'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'EMAIL_HOST_USER': 'synthetic-smtp-user',
            'EMAIL_HOST_PASSWORD': 'synthetic-smtp-password',
            'DEFAULT_FROM_EMAIL': 'orders@example.test',
            'BACKUP_ENABLED': 'True',
            'BACKUP_S3_BUCKET': 'synthetic-backup-bucket',
            'MPESA_ENVIRONMENT': 'production',
            'MPESA_CONSUMER_KEY': 'synthetic-consumer-key',
            'MPESA_CONSUMER_SECRET': 'synthetic-consumer-secret',
            'MPESA_SHORTCODE': '123456',
            'MPESA_PASSKEY': 'synthetic-passkey',
            'MPESA_CALLBACK_URL': 'https://example.test/payments/mpesa/callback/',
        }
        values.update(overrides)
        return values

    def test_production_requires_controller_identity_and_contact(self):
        result = self.import_settings(**self.production_environment(
            PRIVACY_CONTROLLER_NAME='',
            PRIVACY_CONTACT_EMAIL='',
        ))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('approved controller name and privacy contact', result.stderr)

    def test_production_requires_approved_privacy_notice(self):
        result = self.import_settings(**self.production_environment(
            PRIVACY_NOTICE_APPROVED='False',
        ))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('approved privacy notice', result.stderr)

    def test_production_requires_valid_privacy_contact_email(self):
        result = self.import_settings(**self.production_environment(
            PRIVACY_CONTACT_EMAIL='not-an-email-address',
        ))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('valid approved privacy contact email', result.stderr)

    def test_production_rejects_console_and_unknown_notification_providers(self):
        console = self.import_settings(**self.production_environment(
            NOTIFICATION_PROVIDER='console',
        ))
        unsupported = self.import_settings(**self.production_environment(
            NOTIFICATION_PROVIDER='invented-provider',
        ))

        self.assertNotEqual(console.returncode, 0)
        self.assertIn('outbound notification provider', console.stderr)
        self.assertNotEqual(unsupported.returncode, 0)
        self.assertIn('NOTIFICATION_PROVIDER is not supported', unsupported.stderr)

    def test_africas_talking_requires_credentials_and_real_production_account(self):
        missing_key = self.import_settings(**self.production_environment(
            AFRICASTALKING_API_KEY='',
        ))
        sandbox = self.import_settings(**self.production_environment(
            AFRICASTALKING_USERNAME='sandbox',
        ))

        self.assertNotEqual(missing_key.returncode, 0)
        self.assertIn('username and API key are required', missing_key.stderr)
        self.assertNotEqual(sandbox.returncode, 0)
        self.assertIn('cannot use', sandbox.stderr)

    def test_production_boots_with_approved_privacy_and_provider_configuration(self):
        result = self.import_settings(**self.production_environment())

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_uses_cloudinary_as_default_media_storage(self):
        result = self.import_settings(
            script=(
                'import config.settings as s; '
                'print(s.STORAGES["default"]["BACKEND"])'
            ),
            **self.production_environment(),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            'cloudinary_storage.storage.MediaCloudinaryStorage',
        )

    def test_production_rejects_sandbox_mpesa(self):
        result = self.import_settings(**self.production_environment(
            MPESA_ENVIRONMENT='sandbox',
        ))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot start while M-Pesa is configured for sandbox', result.stderr)

    def test_production_requires_transactional_email(self):
        result = self.import_settings(**self.production_environment(
            TRANSACTIONAL_EMAIL_ENABLED='False',
        ))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires verified transactional email delivery', result.stderr)

    def test_production_requires_off_site_backup_job(self):
        result = self.import_settings(**self.production_environment(
            BACKUP_ENABLED='False',
        ))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires the approved encrypted off-site backup job', result.stderr)
