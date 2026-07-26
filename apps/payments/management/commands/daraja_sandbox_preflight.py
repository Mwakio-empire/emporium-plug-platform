from urllib.parse import urlparse

import environ
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from payments.services import MpesaDarajaService


env = environ.Env()


class Command(BaseCommand):
    help = (
        'Validate Daraja sandbox configuration. Add --network to explicitly '
        'request a real sandbox access token without printing it.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--network',
            action='store_true',
            help='Contact the Daraja sandbox token endpoint. No payment is initiated.',
        )

    def handle(self, *args, **options):
        environment = env('MPESA_ENVIRONMENT', default='sandbox').strip().lower()
        if environment != 'sandbox':
            raise CommandError('Refusing preflight: MPESA_ENVIRONMENT must be sandbox.')

        values = {
            'MPESA_CONSUMER_KEY': env('MPESA_CONSUMER_KEY', default='').strip(),
            'MPESA_CONSUMER_SECRET': env('MPESA_CONSUMER_SECRET', default='').strip(),
            'MPESA_SHORTCODE': env('MPESA_SHORTCODE', default='').strip(),
            'MPESA_PASSKEY': env('MPESA_PASSKEY', default='').strip(),
            'MPESA_CALLBACK_URL': env('MPESA_CALLBACK_URL', default='').strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise CommandError(f'Missing required settings: {", ".join(missing)}.')

        callback = urlparse(values['MPESA_CALLBACK_URL'])
        if callback.scheme != 'https' or not callback.hostname:
            raise CommandError('Sandbox callback must be an absolute HTTPS URL.')
        if callback.hostname in {'localhost', '127.0.0.1'}:
            raise CommandError('Sandbox callback must be publicly reachable, not localhost.')

        self.stdout.write(self.style.SUCCESS('PASS: sandbox configuration is structurally valid.'))
        self.stdout.write(f'Callback host: {callback.hostname}')

        if options['network']:
            try:
                MpesaDarajaService.generate_access_token()
            except ValidationError as exc:
                raise CommandError(exc.messages[0]) from None
            self.stdout.write(self.style.SUCCESS(
                'PASS: Daraja sandbox authentication succeeded; token was not displayed.'
            ))
        else:
            self.stdout.write('Network authentication not requested; use --network explicitly.')
