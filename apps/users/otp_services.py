import secrets
import logging
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from .models import OTPVerification

logger = logging.getLogger(__name__)

_MESSAGE_TEMPLATES = {
    OTPVerification.Purpose.SIGNUP: (
        "Your EmporiumPlug verification code is {code}. Expires in {mins} minutes."
    ),
    OTPVerification.Purpose.STAFF_LOGIN: (
        "Your EmporiumPlug staff login code is {code}. Expires in {mins} minutes. "
        "Do not share this code with anyone."
    ),
    OTPVerification.Purpose.PASSWORD_RESET: (
        "Your EmporiumPlug password reset code is {code}. Expires in {mins} minutes. "
        "If you didn't request this, ignore this message."
    ),
    OTPVerification.Purpose.STAFF_INVITE: (
        "Your EmporiumPlug staff activation code is {code}. Expires in {mins} minutes. "
        "Do not share this code with anyone."
    ),
}


class OTPService:
    @staticmethod
    def _cooldown_key(user, purpose):
        # Include account creation time so a deleted/recreated row cannot inherit
        # a previous account's cache cooldown if a database reuses its integer id.
        account_epoch = int(user.date_joined.timestamp() * 1_000_000)
        return f"otp:resend_cooldown:{user.pk}:{account_epoch}:{purpose}"

    @classmethod
    @transaction.atomic
    def generate_and_send(cls, user, purpose=OTPVerification.Purpose.SIGNUP):
        key = cls._cooldown_key(user, purpose)
        if cache.get(key):
            raise ValidationError("Please wait before requesting another code.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        OTPVerification.objects.filter(user=user, purpose=purpose, is_verified=False).delete()
        otp = OTPVerification.objects.create(
            user=user, code=make_password(code), purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=OTPVerification.EXPIRY_MINUTES),
        )
        cache.set(key, True, OTPVerification.RESEND_COOLDOWN_SECONDS)
        message = _MESSAGE_TEMPLATES.get(purpose, _MESSAGE_TEMPLATES[OTPVerification.Purpose.SIGNUP]).format(
            code=code, mins=OTPVerification.EXPIRY_MINUTES,
        )
        try:
            from notifications.catalog import EventType
            from notifications.tasks import queue_sms_event
            queue_sms_event(
                str(user.phone_number), message, EventType.OTP,
                'otp_verification', otp.pk, occurrence=purpose,
                branch=user.branch,
            )
        except Exception:
            logger.error("Failed to queue OTP SMS for user id=%s.", user.id)
        if user.email:
            try:
                from notifications.catalog import EventType
                from notifications.tasks import queue_email_event
                queue_email_event(
                    user.email,
                    'Your Emporium Plug verification code',
                    message,
                    EventType.OTP,
                    'otp_verification', otp.pk,
                    occurrence=purpose,
                    branch=user.branch,
                )
            except Exception:
                logger.error("Failed to queue OTP email for user id=%s.", user.id)
        return otp

    @classmethod
    def verify(cls, user, code, purpose=OTPVerification.Purpose.SIGNUP):
        incorrect_message = None
        with transaction.atomic():
            otp = OTPVerification.objects.select_for_update().filter(
                user=user, purpose=purpose, is_verified=False,
            ).order_by('-created_at').first()
            if otp is None:
                raise ValidationError("No pending verification code. Please request a new one.")
            if otp.is_expired():
                raise ValidationError("This code has expired. Please request a new one.")
            if otp.attempts >= OTPVerification.MAX_ATTEMPTS:
                raise ValidationError("Too many incorrect attempts. Please request a new code.")
            if not check_password(code.strip(), otp.code):
                otp.attempts += 1
                otp.save(update_fields=['attempts'])
                remaining = OTPVerification.MAX_ATTEMPTS - otp.attempts
                incorrect_message = f"Incorrect code. {remaining} attempt(s) remaining."
            else:
                otp.is_verified = True
                otp.save(update_fields=['is_verified'])
                # Only SIGNUP verification should flip is_active -- STAFF_LOGIN and
                # PASSWORD_RESET must never silently reactivate a disabled account.
                if purpose == OTPVerification.Purpose.SIGNUP:
                    if user.role != user.Role.CUSTOMER:
                        raise ValidationError("Signup verification is restricted to customer accounts.")
                    user.is_active = True
                    user.activated_at = timezone.now()
                    user.save(update_fields=['is_active', 'activated_at'])
        # Raise only after the atomic block committed the failed-attempt counter.
        if incorrect_message:
            raise ValidationError(incorrect_message)
        return True
