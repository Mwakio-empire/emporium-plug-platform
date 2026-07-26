from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email


SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'


def validate_report_email_configuration():
    """Fail safely before a scheduled report is rendered or sent."""
    if not settings.REPORT_EMAIL_ENABLED:
        raise ImproperlyConfigured('Scheduled report email is disabled.')

    if not settings.DEFAULT_FROM_EMAIL:
        raise ImproperlyConfigured('DEFAULT_FROM_EMAIL is required for scheduled reports.')
    try:
        validate_email(settings.DEFAULT_FROM_EMAIL)
    except ValidationError as exc:
        raise ImproperlyConfigured(
            'DEFAULT_FROM_EMAIL must be a valid email address.'
        ) from exc

    if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
        raise ImproperlyConfigured('EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.')

    if settings.EMAIL_BACKEND == SMTP_BACKEND:
        missing = [
            name for name in ('EMAIL_HOST', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD')
            if not getattr(settings, name, '')
        ]
        if missing:
            raise ImproperlyConfigured(
                f"Scheduled-report SMTP configuration is missing: {', '.join(missing)}."
            )
