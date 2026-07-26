from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import User


class AuthenticationSecurityService:
    """Persistent account lockout policy shared by HTML and API login."""

    MAX_FAILURES = 5
    LOCKOUT_MINUTES = 15

    @classmethod
    def is_locked(cls, user):
        if not user or not user.locked_until:
            return False
        if user.locked_until > timezone.now():
            return True
        cls.clear_failures(user)
        return False

    @classmethod
    @transaction.atomic
    def record_failure(cls, user):
        if user is None:
            return None
        locked = User.objects.select_for_update().get(pk=user.pk)
        now = timezone.now()
        if locked.locked_until and locked.locked_until <= now:
            locked.failed_login_attempts = 0
            locked.locked_until = None
        locked.failed_login_attempts += 1
        locked.last_failed_login_at = now
        if locked.failed_login_attempts >= cls.MAX_FAILURES:
            locked.locked_until = now + timedelta(minutes=cls.LOCKOUT_MINUTES)
        locked.save(update_fields=[
            'failed_login_attempts', 'last_failed_login_at', 'locked_until',
        ])
        user.failed_login_attempts = locked.failed_login_attempts
        user.locked_until = locked.locked_until
        return locked

    @classmethod
    @transaction.atomic
    def clear_failures(cls, user):
        if user is None:
            return
        User.objects.filter(pk=user.pk).update(
            failed_login_attempts=0,
            locked_until=None,
            last_failed_login_at=None,
        )
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_failed_login_at = None

    @classmethod
    def assert_not_locked(cls, user):
        if cls.is_locked(user):
            raise ValidationError("Sign-in is temporarily locked. Try again later.")
