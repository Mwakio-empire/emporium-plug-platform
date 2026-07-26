import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)
UNVERIFIED_ACCOUNT_EXPIRY_HOURS = 24


@shared_task(name='users.purge_unverified_accounts')
def purge_unverified_accounts():
    """
    Deletes signup accounts (is_active=False) never OTP-verified within
    UNVERIFIED_ACCOUNT_EXPIRY_HOURS. Prevents orphaned rows from blocking
    future signups with the same phone/email. Safe to delete outright --
    unverified accounts never authenticated, so they hold no PROTECT-ed
    FK references (no orders, no stock actions, no audit trail entries).
    """
    from users.models import User
    cutoff = timezone.now() - timedelta(hours=UNVERIFIED_ACCOUNT_EXPIRY_HOURS)
    stale = User.objects.filter(
        role=User.Role.CUSTOMER,
        is_active=False,
        activated_at__isnull=True,
        date_joined__lte=cutoff,
    )
    count = stale.count()
    if count:
        stale.delete()
        logger.info(f"Purged {count} unverified account(s) older than {UNVERIFIED_ACCOUNT_EXPIRY_HOURS}h.")
    else:
        logger.info("Unverified account purge: nothing to clean.")
