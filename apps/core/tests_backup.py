import hashlib
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from core.backup_services import DatabaseBackupManager, DatabaseBackupVerifier


class PostgreSQLBackupTests(SimpleTestCase):
    @override_settings(BACKUP_ENABLED=False)
    def test_disabled_backup_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            DatabaseBackupManager.execute_backup()

    @override_settings(
        BACKUP_ENABLED=True,
        BACKUP_S3_BUCKET='qa-backups',
        BACKUP_S3_PREFIX='database',
        BACKUP_S3_REGION='eu-west-1',
        BACKUP_S3_KMS_KEY_ID='',
        PG_DUMP_BINARY='pg_dump',
        PG_RESTORE_BINARY='pg_restore',
        BACKUP_PGSSLMODE='require',
        BACKUP_COMMAND_TIMEOUT_SECONDS=30,
        DATABASES={'default': {
            'ENGINE': 'django.db.backends.postgresql', 'NAME': 'retail',
            'HOST': 'db.internal', 'PORT': '5432', 'USER': 'backup',
            'PASSWORD': 'secret-not-logged',
        }},
    )
    @patch('core.backup_services.boto3.client')
    @patch('core.backup_services.subprocess.run')
    def test_pg_dump_archive_is_encrypted_uploaded_and_removed(self, run, boto_client):
        def write_backup(command, **kwargs):
            Path(command[command.index('--file') + 1]).write_bytes(b'postgres-backup')
            return Mock(returncode=0)

        run.side_effect = write_backup
        s3 = boto_client.return_value
        result = DatabaseBackupManager.execute_backup()

        command = run.call_args.args[0]
        self.assertIn('--format=custom', command)
        self.assertNotIn('secret-not-logged', command)
        self.assertEqual(run.call_args.kwargs['env']['PGSSLMODE'], 'require')
        upload = s3.upload_file.call_args
        self.assertEqual(upload.args[1], 'qa-backups')
        self.assertEqual(upload.kwargs['ExtraArgs']['ServerSideEncryption'], 'AES256')
        self.assertFalse(Path(upload.args[0]).exists())
        self.assertEqual(result['bytes'], len(b'postgres-backup'))


@override_settings(
    BACKUP_S3_BUCKET='qa-backups',
    BACKUP_S3_PREFIX='database',
    BACKUP_S3_REGION='eu-west-1',
    PG_RESTORE_BINARY='pg_restore',
    BACKUP_COMMAND_TIMEOUT_SECONDS=30,
)
class PostgreSQLBackupVerificationTests(SimpleTestCase):
    @patch('core.backup_services.boto3.client')
    @patch('core.backup_services.subprocess.run')
    def test_encrypted_archive_checksum_and_catalog_are_verified(self, run, boto_client):
        payload = b'postgres-backup'
        digest = hashlib.sha256(payload).hexdigest()
        s3 = boto_client.return_value
        s3.head_object.return_value = {
            'ServerSideEncryption': 'AES256',
            'Metadata': {'sha256': digest},
        }

        def download(_bucket, _key, destination):
            Path(destination).write_bytes(payload)

        s3.download_file.side_effect = download
        result = DatabaseBackupVerifier.verify_s3_archive('database/postgres.dump')

        archive_path = Path(run.call_args.args[0][-1])
        self.assertEqual(run.call_args.args[0][:2], ['pg_restore', '--list'])
        self.assertFalse(archive_path.exists())
        self.assertEqual(result['sha256'], digest)
        self.assertEqual(result['bytes'], len(payload))

    @patch('core.backup_services.boto3.client')
    @patch('core.backup_services.subprocess.run')
    def test_checksum_mismatch_fails_before_pg_restore(self, run, boto_client):
        s3 = boto_client.return_value
        s3.head_object.return_value = {
            'ServerSideEncryption': 'aws:kms',
            'Metadata': {'sha256': hashlib.sha256(b'expected').hexdigest()},
        }

        def download(_bucket, _key, destination):
            Path(destination).write_bytes(b'corrupt')

        s3.download_file.side_effect = download
        with self.assertRaisesMessage(RuntimeError, 'checksum verification failed'):
            DatabaseBackupVerifier.verify_s3_archive('database/postgres.dump')
        run.assert_not_called()

    @patch('core.backup_services.boto3.client')
    def test_unencrypted_archive_is_rejected_before_download(self, boto_client):
        s3 = boto_client.return_value
        s3.head_object.return_value = {
            'Metadata': {'sha256': hashlib.sha256(b'archive').hexdigest()},
        }
        with self.assertRaisesMessage(RuntimeError, 'server-side encryption'):
            DatabaseBackupVerifier.verify_s3_archive('database/postgres.dump')
        s3.download_file.assert_not_called()

    @patch('core.backup_services.boto3.client')
    @patch('core.backup_services.subprocess.run')
    def test_unreadable_catalog_fails_and_removes_archive(self, run, boto_client):
        payload = b'not-a-pg-dump'
        digest = hashlib.sha256(payload).hexdigest()
        s3 = boto_client.return_value
        s3.head_object.return_value = {
            'ServerSideEncryption': 'AES256',
            'Metadata': {'sha256': digest},
        }

        def download(_bucket, _key, destination):
            Path(destination).write_bytes(payload)

        s3.download_file.side_effect = download
        run.side_effect = subprocess.CalledProcessError(1, 'pg_restore')
        with self.assertRaisesMessage(RuntimeError, 'could not read'):
            DatabaseBackupVerifier.verify_s3_archive('database/postgres.dump')
        self.assertFalse(Path(run.call_args.args[0][-1]).exists())

    @patch('core.backup_services.boto3.client')
    def test_object_outside_configured_prefix_is_rejected(self, boto_client):
        with self.assertRaisesMessage(ValueError, 'outside the configured backup prefix'):
            DatabaseBackupVerifier.verify_s3_archive('other/postgres.dump')
        boto_client.assert_not_called()
