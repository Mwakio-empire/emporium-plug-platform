from email.message import Message
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from core.media_verification import MediaVerificationError, verify_cloudinary_round_trip


class CloudinaryMediaVerificationTests(SimpleTestCase):
    @patch('core.media_verification.uploader.destroy')
    @patch('core.media_verification.urlopen')
    @patch('core.media_verification.uploader.upload')
    @patch('core.media_verification.cloudinary_config')
    def test_round_trip_uploads_delivers_and_deletes(
        self,
        configured,
        upload,
        open_url,
        destroy,
    ):
        configured.return_value = MagicMock(
            cloud_name='verified-cloud', api_key='key', api_secret='secret'
        )
        upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/verified-cloud/image/upload/test.png'
        }
        headers = Message()
        headers['Content-Type'] = 'image/png'
        delivered = MagicMock(status=200, headers=headers)
        delivered.read.return_value = b'png-bytes'
        open_url.return_value.__enter__.return_value = delivered
        destroy.return_value = {'result': 'ok'}

        summary = verify_cloudinary_round_trip(timeout_seconds=5)

        self.assertEqual(summary['cloud_name'], 'verified-cloud')
        self.assertEqual(summary['delivery_host'], 'res.cloudinary.com')
        self.assertEqual(summary['delivered_bytes'], 9)
        upload.assert_called_once()
        destroy.assert_called_once()

    @patch('core.media_verification.uploader.destroy')
    @patch('core.media_verification.urlopen', side_effect=TimeoutError)
    @patch('core.media_verification.uploader.upload')
    @patch('core.media_verification.cloudinary_config')
    def test_delivery_failure_still_deletes_synthetic_asset(
        self,
        configured,
        upload,
        _open_url,
        destroy,
    ):
        configured.return_value = MagicMock(
            cloud_name='verified-cloud', api_key='key', api_secret='secret'
        )
        upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/verified-cloud/image/upload/test.png'
        }
        destroy.return_value = {'result': 'ok'}

        with self.assertRaisesMessage(MediaVerificationError, 'verification failed'):
            verify_cloudinary_round_trip(timeout_seconds=5)

        destroy.assert_called_once()

    def test_command_requires_explicit_remote_write_confirmation(self):
        with self.assertRaisesMessage(CommandError, 'Refusing remote write'):
            call_command('verify_cloudinary_media', stdout=StringIO())
