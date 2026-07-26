import hashlib
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class DatabaseBackupManager:
    """Create a PostgreSQL custom-format logical backup in off-site S3 storage."""

    @classmethod
    def execute_backup(cls):
        if not settings.BACKUP_ENABLED:
            raise ImproperlyConfigured('Application-managed backups are disabled.')
        database = settings.DATABASES['default']
        if database['ENGINE'] != 'django.db.backends.postgresql':
            raise ImproperlyConfigured('PostgreSQL is required for production backups.')
        if not settings.BACKUP_S3_BUCKET:
            raise ImproperlyConfigured('BACKUP_S3_BUCKET is required when backups are enabled.')

        with tempfile.NamedTemporaryFile(suffix='.dump', delete=False) as handle:
            backup_path = Path(handle.name)
        try:
            command = [
                settings.PG_DUMP_BINARY,
                '--format=custom',
                '--no-owner',
                '--no-privileges',
                '--file', str(backup_path),
                '--host', str(database.get('HOST') or ''),
                '--port', str(database.get('PORT') or '5432'),
                '--username', str(database.get('USER') or ''),
                str(database.get('NAME') or ''),
            ]
            process_env = os.environ.copy()
            process_env['PGPASSWORD'] = str(database.get('PASSWORD') or '')
            subprocess.run(
                command, check=True, env=process_env, capture_output=True,
                timeout=settings.BACKUP_COMMAND_TIMEOUT_SECONDS,
            )
            if not backup_path.exists() or backup_path.stat().st_size == 0:
                raise RuntimeError('pg_dump completed without a backup artifact.')

            digest = hashlib.sha256(backup_path.read_bytes()).hexdigest()
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            object_key = (
                f"{settings.BACKUP_S3_PREFIX.rstrip('/')}/"
                f"postgres-{timestamp}-{digest[:12]}.dump"
            )
            extra_args = {
                'ContentType': 'application/octet-stream',
                'Metadata': {'sha256': digest, 'format': 'pg_dump-custom'},
                'ServerSideEncryption': 'AES256',
            }
            if settings.BACKUP_S3_KMS_KEY_ID:
                extra_args.update({
                    'ServerSideEncryption': 'aws:kms',
                    'SSEKMSKeyId': settings.BACKUP_S3_KMS_KEY_ID,
                })
            boto3.client('s3', region_name=settings.BACKUP_S3_REGION).upload_file(
                str(backup_path), settings.BACKUP_S3_BUCKET, object_key,
                ExtraArgs=extra_args,
            )
            size = backup_path.stat().st_size
            logger.info('PostgreSQL logical backup uploaded | ObjectKey=%s | Bytes=%s', object_key, size)
            return {'object_key': object_key, 'sha256': digest, 'bytes': size}
        finally:
            backup_path.unlink(missing_ok=True)
