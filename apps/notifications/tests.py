from unittest.mock import patch
from io import BytesIO
from urllib.error import HTTPError
from datetime import timedelta

from django.test import TestCase, override_settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from notifications.catalog import EventType
from notifications.models import Notification, NotificationDeliveryAttempt
from notifications.services import NotificationEngineService, ProviderResult, normalize_phone
from notifications.tasks import queue_email_event, queue_sms_event, send_email_task, send_sms_task
from users.models import User


class NotificationProviderTests(TestCase):
    def test_phone_normalization_is_kenya_scoped(self):
        self.assertEqual(normalize_phone('0711 223 344'), '+254711223344')

    @override_settings(NOTIFICATION_PROVIDER='console')
    @patch('notifications.services.urlopen')
    def test_safe_provider_never_contacts_external_gateway(self, mocked_urlopen):
        result = NotificationEngineService.deliver_sms('+254711223344', 'Test message')
        self.assertTrue(result.success)
        self.assertTrue(result.suppressed)
        mocked_urlopen.assert_not_called()

    @override_settings(
        NOTIFICATION_PROVIDER='africastalking',
        AFRICASTALKING_USERNAME='sandbox', AFRICASTALKING_API_KEY='test-key',
        AFRICASTALKING_SENDER_ID='',
    )
    @patch('notifications.services.urlopen')
    def test_africas_talking_success_is_parsed_without_message_body_logging(self, mocked_urlopen):
        response = BytesIO(__import__('json').dumps({
            'SMSMessageData': {'Recipients': [{
                'status': 'Success', 'statusCode': 101,
                'messageId': 'AT-123', 'cost': 'KES 0.80',
            }]},
        }).encode('utf-8'))
        response.status = 201
        mocked_urlopen.return_value.__enter__.return_value = response
        result = NotificationEngineService.deliver_sms('+254711223344', 'Private body')
        self.assertTrue(result.success)
        self.assertEqual(result.message_id, 'AT-123')
        self.assertNotIn('Private body', result.response_summary)
        self.assertEqual(mocked_urlopen.call_count, 1)

    @override_settings(
        NOTIFICATION_PROVIDER='africastalking',
        AFRICASTALKING_USERNAME='sandbox', AFRICASTALKING_API_KEY='bad-key',
        AFRICASTALKING_SENDER_ID='',
    )
    @patch('notifications.services.urlopen')
    def test_africas_talking_http_rejection_is_not_a_network_error(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            'https://api.sandbox.africastalking.com/version1/messaging',
            401, 'Unauthorized', {}, BytesIO(b''),
        )
        result = NotificationEngineService.deliver_sms('+254711223344', 'Private body')
        self.assertFalse(result.success)
        self.assertEqual(result.status, 'HTTP_401')
        self.assertFalse(result.retryable)


class DurableNotificationTests(TestCase):
    def delivery_in_progress(self, *, expires_at):
        return Notification.objects.create(
            event_type=EventType.PICKUP_READY,
            template_key='pickup.ready.sms',
            recipient='+254711223344',
            recipient_hash='a' * 64,
            reference_type='order',
            reference_id='20',
            dedupe_key='pickup-ready-order-20',
            message_fingerprint='b' * 64,
            status=Notification.Status.SENDING,
            attempt_count=1,
            delivery_lease_token='active-lease',
            delivery_lease_expires_at=expires_at,
        )

    @patch('notifications.tasks.NotificationEngineService.deliver_sms')
    def test_active_delivery_lease_blocks_concurrent_duplicate(self, mocked_sms):
        notification = self.delivery_in_progress(
            expires_at=timezone.now() + timedelta(minutes=1),
        )

        result = send_sms_task(
            '+254711223344', 'Order ready', EventType.PICKUP_READY,
            'order', '20', notification.dedupe_key,
        )

        self.assertFalse(result)
        mocked_sms.assert_not_called()
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.SENDING)
        self.assertEqual(notification.attempt_count, 1)

    @patch('notifications.tasks.NotificationEngineService.deliver_sms')
    def test_expired_delivery_lease_requires_manual_reconciliation(self, mocked_sms):
        notification = self.delivery_in_progress(
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        result = send_sms_task(
            '+254711223344', 'Order ready', EventType.PICKUP_READY,
            'order', '20', notification.dedupe_key,
        )

        self.assertFalse(result)
        mocked_sms.assert_not_called()
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.MANUAL_FOLLOWUP)
        self.assertEqual(notification.last_error_code, 'DELIVERY_OUTCOME_UNKNOWN')

    @override_settings(TRANSACTIONAL_EMAIL_ENABLED=False)
    @patch('notifications.tasks.EmailMessage.send')
    def test_safe_email_is_suppressed_without_contacting_backend(self, mocked_send):
        result = send_email_task(
            'buyer@example.test', 'Order received', 'Private order details',
            EventType.ORDER_PLACED, 'order', '19', 'email-order-19',
        )
        self.assertTrue(result)
        mocked_send.assert_not_called()
        notification = Notification.objects.get()
        self.assertEqual(notification.channel, Notification.Channel.EMAIL)
        self.assertEqual(notification.status, Notification.Status.SUPPRESSED)
        self.assertFalse(hasattr(notification, 'message'))

    @override_settings(
        TRANSACTIONAL_EMAIL_ENABLED=True,
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='orders@emporium.test',
    )
    def test_enabled_email_sends_once_and_records_delivery(self):
        args = (
            'buyer@example.test', 'Order received', 'Track your order safely.',
            EventType.ORDER_PLACED, 'order', '20', 'email-order-20',
        )
        self.assertTrue(send_email_task(*args))
        self.assertTrue(send_email_task(*args))
        self.assertEqual(len(mail.outbox), 1)
        notification = Notification.objects.get()
        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertEqual(notification.delivery_attempts.count(), 1)

    @override_settings(NOTIFICATION_PROVIDER='console')
    def test_safe_delivery_is_durable_and_contains_no_message_body(self):
        result = send_sms_task(
            '+254711223344', 'OTP 123456', EventType.OTP,
            'user', '15', 'otp-user-15-login-1',
        )
        self.assertTrue(result)
        notification = Notification.objects.get()
        self.assertEqual(notification.status, Notification.Status.SUPPRESSED)
        self.assertEqual(notification.attempt_count, 1)
        self.assertFalse(hasattr(notification, 'message'))
        attempt = notification.delivery_attempts.get()
        self.assertEqual(attempt.status, NotificationDeliveryAttempt.Status.SUPPRESSED)
        self.assertNotIn('123456', attempt.response_summary)

    @override_settings(NOTIFICATION_PROVIDER='console')
    def test_explicit_dedupe_key_prevents_duplicate_delivery(self):
        args = (
            '+254711223344', 'Order ready', EventType.PICKUP_READY,
            'order', '20', 'pickup-ready-order-20',
        )
        self.assertTrue(send_sms_task(*args))
        self.assertTrue(send_sms_task(*args))
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(NotificationDeliveryAttempt.objects.count(), 1)

    @patch('notifications.tasks.NotificationEngineService.deliver_sms')
    def test_permanent_failure_enters_manual_followup(self, mocked_sms):
        mocked_sms.return_value = ProviderResult(
            success=False, provider='africastalking', status='Rejected',
            error_code='INVALID_RECIPIENT', retryable=False,
        )
        self.assertFalse(send_sms_task(
            '+254711223344', 'Status update', EventType.DELIVERY_STATUS,
            'order', '21', 'delivery-status-order-21',
        ))
        notification = Notification.objects.get()
        self.assertEqual(notification.status, Notification.Status.MANUAL_FOLLOWUP)
        self.assertEqual(notification.last_error_code, 'INVALID_RECIPIENT')

    @override_settings(WHATSAPP_FALLBACK_ENABLED=True)
    @patch('notifications.tasks.NotificationEngineService.deliver_whatsapp')
    @patch('notifications.tasks.NotificationEngineService.deliver_sms')
    def test_critical_event_uses_approved_whatsapp_fallback_only(self, mocked_sms, mocked_whatsapp):
        mocked_sms.return_value = ProviderResult(
            success=False, provider='africastalking', status='Rejected',
            error_code='PROVIDER_REJECTED', retryable=False,
        )
        mocked_whatsapp.return_value = ProviderResult(
            success=True, provider='whatsapp', status='HTTP_200',
        )
        self.assertTrue(send_sms_task(
            '+254711223344', 'Payment received', EventType.PAYMENT_CONFIRMED,
            'order', '22', 'payment-confirmed-order-22',
        ))
        notification = Notification.objects.get()
        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertEqual(notification.channel, Notification.Channel.WHATSAPP)
        self.assertEqual(notification.delivery_attempts.count(), 2)


class NotificationOperationsTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Notification S18', location='Nairobi')
        self.other_branch = Branch.objects.create(name='Notification OTC', location='Nairobi')
        self.manager = User.objects.create_user(
            username='notify-manager', phone_number='+254700994001',
            email='notify-manager@example.test', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )

    def failed(self, branch, reference):
        return Notification.objects.create(
            event_type=EventType.DELIVERY_STATUS,
            template_key='delivery.status',
            criticality=Notification.Criticality.IMPORTANT,
            recipient='+254711223344', recipient_hash='a' * 64,
            branch=branch, reference_type='order', reference_id=reference,
            dedupe_key=(reference * 64)[:64], message_fingerprint='b' * 64,
            status=Notification.Status.MANUAL_FOLLOWUP,
            attempt_count=1, last_error_code='INVALID_RECIPIENT',
        )

    def test_manager_queue_is_branch_scoped_and_resolution_is_audited(self):
        own = self.failed(self.branch, '1')
        other = self.failed(self.other_branch, '2')
        self.client.force_login(self.manager)
        page = self.client.get(reverse('notifications:operations'))
        self.assertContains(page, 'order 1')
        self.assertNotContains(page, 'order 2')
        denied = self.client.post(reverse('notifications:operations'), {
            'notification_id': other.pk, 'resolution_note': 'Called and confirmed.',
        })
        self.assertEqual(denied.status_code, 404)
        response = self.client.post(reverse('notifications:operations'), {
            'notification_id': own.pk,
            'resolution_note': 'Customer contacted by store phone.',
        }, follow=True)
        self.assertContains(response, 'Manual notification follow-up recorded.')
        own.refresh_from_db()
        self.assertEqual(own.status, Notification.Status.RESOLVED_MANUAL)
        self.assertEqual(own.followup_resolved_by, self.manager)
        self.assertIsNotNone(own.followup_resolved_at)

    @patch('notifications.tasks.send_sms_task.delay')
    def test_event_queue_is_deduplicated_before_celery(self, mocked_delay):
        first = queue_sms_event(
            '+254711223344', 'Order ready', EventType.PICKUP_READY,
            'order', '40', branch=self.branch,
        )
        second = queue_sms_event(
            '+254711223344', 'Order ready', EventType.PICKUP_READY,
            'order', '40', branch=self.branch,
        )
        self.assertTrue(first)
        self.assertFalse(second)
        mocked_delay.assert_called_once_with('+254711223344', 'Order ready')
        notification = Notification.objects.get()
        self.assertEqual(notification.event_type, EventType.PICKUP_READY)
        self.assertEqual(notification.branch, self.branch)
