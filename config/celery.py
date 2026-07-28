import logging
import os

from celery import Celery
from celery.schedules import crontab


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

TASK_RETRY_KWARGS = dict(
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)

app = Celery('dynamic_retail_system')
logger = logging.getLogger(__name__)
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """Diagnostic echo confirming worker connectivity."""
    logger.info('Celery connectivity diagnostic completed | TaskID=%s', self.request.id)


# Beat schedules are centralized here. Run exactly one Beat process.
app.conf.beat_schedule = {
    'record-async-pipeline-heartbeat-every-minute': {
        'task': 'core.tasks.record_async_pipeline_heartbeat',
        'schedule': crontab(minute='*'),
    },
    'dispatch-due-scheduled-reports-hourly': {
        'task': 'reports.tasks.dispatch_due_scheduled_reports',
        'schedule': crontab(minute=5),
    },
    # Alert only when a branch stock row crosses into a low-stock state.
    'send-low-stock-alerts-every-hour': {
        'task': 'inventory.send_branch_low_stock_alerts',
        'schedule': crontab(minute=0),
    },
    'send-pickup-reminders-every-hour': {
        'task': 'orders.send_pickup_reminders',
        'schedule': crontab(minute=15),
    },
    'auto-cancel-unresolved-pickups-every-hour': {
        'task': 'orders.auto_cancel_unresolved_pickups',
        'schedule': crontab(minute=45),
    },
    'cancel-abandoned-pending-orders-every-five-minutes': {
        'task': 'orders.cancel_abandoned_pending_orders',
        'schedule': crontab(minute='*/5'),
    },
    'purge-unverified-accounts-daily': {
        'task': 'users.purge_unverified_accounts',
        'schedule': crontab(hour=3, minute=0),
    },
}
