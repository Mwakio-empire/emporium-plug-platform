import logging

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from config.celery import TASK_RETRY_KWARGS
from core.health import ASYNC_PIPELINE_HEARTBEAT_KEY

logger = logging.getLogger(__name__)


@shared_task(name='core.tasks.record_async_pipeline_heartbeat')
def record_async_pipeline_heartbeat():
    """Prove that Beat scheduled a task and a worker executed it."""
    timestamp = timezone.now().timestamp()
    cache.set(
        ASYNC_PIPELINE_HEARTBEAT_KEY,
        timestamp,
        timeout=settings.ASYNC_HEARTBEAT_MAX_AGE_SECONDS * 2,
    )
    logger.info('Asynchronous task pipeline heartbeat recorded')
    return timestamp


@shared_task(name='core.tasks.execute_automated_s3_backup', **TASK_RETRY_KWARGS)
def execute_automated_s3_backup(self):
    """Create one off-site backup when invoked by the platform scheduler."""
    try:
        from core.backup_services import DatabaseBackupManager
        result = DatabaseBackupManager.execute_backup()
        logger.info(
            'Automated PostgreSQL backup completed | ObjectKey=%s | Bytes=%s',
            result['object_key'], result['bytes'],
        )
        return result
    except Exception as e:
        logger.error('Automated PostgreSQL backup failed | ExceptionType=%s', type(e).__name__)
        raise self.retry(exc=e)
