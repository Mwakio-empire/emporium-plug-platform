import hashlib
import hmac
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


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
        for field in ('NAME', 'HOST', 'USER'):
            if not database.get(field):
                raise ImproperlyConfigured(f'Database {field} is required for PostgreSQL backups.')

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
            process_env['PGSSLMODE'] = settings.BACKUP_PGSSLMODE
            subprocess.run(
                command, check=True, env=process_env, capture_output=True,
                timeout=settings.BACKUP_COMMAND_TIMEOUT_SECONDS,
            )
            if not backup_path.exists() or backup_path.stat().st_size == 0:
                raise RuntimeError('pg_dump completed without a backup artifact.')

            digest = _sha256_file(backup_path)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
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


class DatabaseBackupVerifier:
    """Download and verify an off-site archive without restoring any data."""

    @classmethod
    def verify_s3_archive(cls, object_key: str):
        if not settings.BACKUP_S3_BUCKET:
            raise ImproperlyConfigured('BACKUP_S3_BUCKET is required to verify a backup.')
        if not object_key or object_key.startswith('/') or '..' in object_key.split('/'):
            raise ValueError('A valid backup object key is required.')
        approved_prefix = f"{settings.BACKUP_S3_PREFIX.rstrip('/')}/"
        if not object_key.startswith(approved_prefix):
            raise ValueError('Backup object key is outside the configured backup prefix.')

        s3 = boto3.client('s3', region_name=settings.BACKUP_S3_REGION)
        metadata = s3.head_object(Bucket=settings.BACKUP_S3_BUCKET, Key=object_key)
        encryption = metadata.get('ServerSideEncryption')
        if encryption not in {'AES256', 'aws:kms'}:
            raise RuntimeError('Backup object is not protected by approved server-side encryption.')
        expected_digest = (metadata.get('Metadata') or {}).get('sha256', '').lower()
        if len(expected_digest) != 64 or any(char not in '0123456789abcdef' for char in expected_digest):
            raise RuntimeError('Backup object has no valid SHA-256 metadata.')

        with tempfile.NamedTemporaryFile(suffix='.dump', delete=False) as handle:
            archive_path = Path(handle.name)
        try:
            s3.download_file(settings.BACKUP_S3_BUCKET, object_key, str(archive_path))
            actual_digest = _sha256_file(archive_path)
            if not hmac.compare_digest(actual_digest, expected_digest):
                raise RuntimeError('Backup checksum verification failed.')

            try:
                subprocess.run(
                    [settings.PG_RESTORE_BINARY, '--list', str(archive_path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=settings.BACKUP_COMMAND_TIMEOUT_SECONDS,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError('pg_restore could not read the backup archive catalog.') from exc
            size = archive_path.stat().st_size
            logger.info(
                'PostgreSQL logical backup verified | ObjectKey=%s | Bytes=%s',
                object_key,
                size,
            )
            return {'object_key': object_key, 'sha256': actual_digest, 'bytes': size}
        finally:
            archive_path.unlink(missing_ok=True)
