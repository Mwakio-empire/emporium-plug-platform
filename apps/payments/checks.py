from urllib.parse import urlparse

import environ
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


env = environ.Env()


@register(Tags.security, deploy=True)
def check_daraja_deployment_configuration(app_configs, **kwargs):
    errors = []
    environment = env('MPESA_ENVIRONMENT', default='sandbox').strip().lower()
    if environment not in {'sandbox', 'production'}:
        errors.append(Error(
            'MPESA_ENVIRONMENT must be sandbox or production.',
            id='payments.E001',
        ))

    required = {
        'MPESA_CONSUMER_KEY': env('MPESA_CONSUMER_KEY', default='').strip(),
        'MPESA_CONSUMER_SECRET': env('MPESA_CONSUMER_SECRET', default='').strip(),
        'MPESA_SHORTCODE': env('MPESA_SHORTCODE', default='').strip(),
        'MPESA_PASSKEY': env('MPESA_PASSKEY', default='').strip(),
        'MPESA_CALLBACK_URL': env('MPESA_CALLBACK_URL', default='').strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        check_class = Error if environment == 'production' else Warning
        check_id = 'payments.E004' if environment == 'production' else 'payments.W001'
        errors.append(check_class(
            f'Daraja deployment settings are incomplete: {", ".join(missing)}.',
            hint='Supply sandbox values in staging and production values only in production.',
            id=check_id,
        ))

    callback_url = required['MPESA_CALLBACK_URL']
    if callback_url:
        parsed = urlparse(callback_url)
        if parsed.scheme != 'https' and (environment == 'production' or not settings.DEBUG):
            errors.append(Error(
                'MPESA_CALLBACK_URL must use HTTPS outside local development.',
                id='payments.E002',
            ))
        if parsed.hostname in {'127.0.0.1', 'localhost'} and not settings.DEBUG:
            errors.append(Error(
                'MPESA_CALLBACK_URL must be publicly reachable outside local development.',
                id='payments.E003',
            ))
    return errors
