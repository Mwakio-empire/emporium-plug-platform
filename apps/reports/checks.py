from django.conf import settings
from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured

from .email_config import validate_report_email_configuration


@register()
def report_email_configuration_check(app_configs, **kwargs):
    if not settings.REPORT_EMAIL_ENABLED:
        return []
    try:
        validate_report_email_configuration()
    except ImproperlyConfigured as exc:
        return [Error(str(exc), id='reports.E001')]
    return []
