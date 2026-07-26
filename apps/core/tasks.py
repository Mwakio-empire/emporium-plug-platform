# apps/core/tasks.py (create this file)

from celery import shared_task
import logging
from config.celery import TASK_RETRY_KWARGS

logger = logging.getLogger(__name__)


@shared_task(name='core.tasks.execute_automated_s3_backup', **TASK_RETRY_KWARGS)
def execute_automated_s3_backup(self):
    """
    Automated S3 database backup task.
    Called nightly by Celery Beat at 2AM (config/celery.py beat_schedule).
    """
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
