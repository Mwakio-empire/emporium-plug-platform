from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from core.backup_services import DatabaseBackupManager


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
        upload = s3.upload_file.call_args
        self.assertEqual(upload.args[1], 'qa-backups')
        self.assertEqual(upload.kwargs['ExtraArgs']['ServerSideEncryption'], 'AES256')
        self.assertFalse(Path(upload.args[0]).exists())
        self.assertEqual(result['bytes'], len(b'postgres-backup'))
