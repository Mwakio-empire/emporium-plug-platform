import hashlib
import hmac
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.exceptions import ValidationError


KENYAN_PHONE = re.compile(r'^\+254\d{9}$')


def normalize_phone(value):
    phone = re.sub(r'[\s()-]', '', str(value or '').strip())
    if phone.startswith('0'):
        phone = '+254' + phone[1:]
    elif phone.startswith('254'):
        phone = '+' + phone
    if not KENYAN_PHONE.fullmatch(phone):
        raise ValidationError('Use a valid Kenyan phone number in +254 format.')
    return phone


def keyed_digest(value):
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'), str(value).encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    provider: str
    status: str
    message_id: str = ''
    error_code: str = ''
    response_summary: str = ''
    retryable: bool = False
    suppressed: bool = False


class NotificationEngineService:
    """One provider call per delivery attempt; retry policy lives in Celery."""

    @classmethod
    def deliver_sms(cls, phone_number, message_text):
        phone = normalize_phone(phone_number)
        if not str(message_text or '').strip():
            raise ValidationError('Notification message cannot be empty.')
        provider = settings.NOTIFICATION_PROVIDER.lower()
        if provider == 'console':
            return ProviderResult(
                success=True, provider='console', status='SUPPRESSED_DEVELOPMENT',
                response_summary='No external contact; safe provider active.',
                suppressed=True,
            )
        if provider != 'africastalking':
            raise ValidationError('Unsupported notification provider configuration.')

        endpoint = (
            'https://api.sandbox.africastalking.com/version1/messaging'
            if settings.AFRICASTALKING_USERNAME.lower() == 'sandbox'
            else 'https://api.africastalking.com/version1/messaging'
        )
        payload = {
            'username': settings.AFRICASTALKING_USERNAME,
            'to': phone,
            'message': message_text,
        }
        if settings.AFRICASTALKING_SENDER_ID:
            payload['from'] = settings.AFRICASTALKING_SENDER_ID
        try:
            response = requests.post(
                endpoint, data=payload,
                headers={
                    'ApiKey': settings.AFRICASTALKING_API_KEY,
                    'Accept': 'application/json',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=10,
            )
            data = response.json()
            recipient = (data.get('SMSMessageData', {}).get('Recipients') or [{}])[0]
            status = str(recipient.get('status') or f'HTTP_{response.status_code}')[:80]
            success = response.ok and status in {'Success', 'Sent'}
            return ProviderResult(
                success=success,
                provider='africastalking',
                status=status,
                message_id=str(recipient.get('messageId') or '')[:120],
                error_code=str(recipient.get('statusCode') or '')[:80] if not success else '',
                response_summary=(
                    f"http={response.status_code}; status={status}; "
                    f"cost={str(recipient.get('cost') or '')[:40]}"
                )[:300],
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        except (requests.RequestException, ValueError) as exc:
            return ProviderResult(
                success=False, provider='africastalking', status='NETWORK_ERROR',
                error_code=type(exc).__name__[:80], retryable=True,
                response_summary='Provider request failed before a valid acknowledgement.',
            )

    @classmethod
    def deliver_whatsapp(cls, phone_number, message_text):
        phone = normalize_phone(phone_number)
        if not settings.WHATSAPP_FALLBACK_ENABLED:
            return ProviderResult(
                success=False, provider='whatsapp', status='DISABLED',
                error_code='FALLBACK_DISABLED', retryable=False,
            )
        if not settings.WHATSAPP_API_URL or not settings.WHATSAPP_BEARER_TOKEN:
            return ProviderResult(
                success=False, provider='whatsapp', status='UNCONFIGURED',
                error_code='FALLBACK_UNCONFIGURED', retryable=False,
            )
        try:
            response = requests.post(
                settings.WHATSAPP_API_URL,
                json={
                    'messaging_product': 'whatsapp', 'recipient_type': 'individual',
                    'to': phone.removeprefix('+'), 'type': 'text',
                    'text': {'body': message_text},
                },
                headers={
                    'Authorization': f'Bearer {settings.WHATSAPP_BEARER_TOKEN}',
                    'Content-Type': 'application/json',
                }, timeout=10,
            )
            return ProviderResult(
                success=response.status_code in {200, 201}, provider='whatsapp',
                status=f'HTTP_{response.status_code}',
                retryable=response.status_code >= 500 or response.status_code == 429,
                response_summary=f'http={response.status_code}',
            )
        except requests.RequestException as exc:
            return ProviderResult(
                success=False, provider='whatsapp', status='NETWORK_ERROR',
                error_code=type(exc).__name__[:80], retryable=True,
                response_summary='Provider request failed before a valid acknowledgement.',
            )

    @classmethod
    def send_sms(cls, phone_number, message_text):
        """Compatibility wrapper for direct callers; durable tasks use deliver_sms."""
        return cls.deliver_sms(phone_number, message_text).success
