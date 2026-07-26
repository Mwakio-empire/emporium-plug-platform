import os
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


SANDBOX_ENV = {
    'MPESA_ENVIRONMENT': 'sandbox',
    'MPESA_CONSUMER_KEY': 'sandbox-key',
    'MPESA_CONSUMER_SECRET': 'sandbox-secret',
    'MPESA_SHORTCODE': '174379',
    'MPESA_PASSKEY': 'sandbox-passkey',
    'MPESA_CALLBACK_URL': 'https://staging.example.test/payments/mpesa/callback/',
}


class DarajaSandboxPreflightCommandTests(SimpleTestCase):
    @patch.dict(os.environ, SANDBOX_ENV)
    def test_offline_preflight_never_contacts_provider(self):
        output = StringIO()
        with patch(
            'payments.services.MpesaDarajaService.generate_access_token'
        ) as mock_token:
            call_command('daraja_sandbox_preflight', stdout=output)
        mock_token.assert_not_called()
        self.assertIn('structurally valid', output.getvalue())
        self.assertIn('Network authentication not requested', output.getvalue())

    @patch.dict(os.environ, SANDBOX_ENV)
    def test_network_preflight_is_explicit_and_does_not_print_token(self):
        output = StringIO()
        with patch(
            'payments.services.MpesaDarajaService.generate_access_token',
            return_value='secret-token-that-must-not-be-printed',
        ) as mock_token:
            call_command('daraja_sandbox_preflight', '--network', stdout=output)
        mock_token.assert_called_once_with()
        self.assertIn('authentication succeeded', output.getvalue())
        self.assertNotIn('secret-token-that-must-not-be-printed', output.getvalue())

    @patch.dict(os.environ, {**SANDBOX_ENV, 'MPESA_CALLBACK_URL': 'http://localhost/callback/'})
    def test_preflight_rejects_non_public_callback(self):
        with self.assertRaises(CommandError):
            call_command('daraja_sandbox_preflight', stdout=StringIO())

    @patch.dict(os.environ, {**SANDBOX_ENV, 'MPESA_ENVIRONMENT': 'production'})
    def test_preflight_refuses_production_environment(self):
        with self.assertRaises(CommandError):
            call_command('daraja_sandbox_preflight', stdout=StringIO())
