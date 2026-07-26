from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from branches.models import Branch
from notifications.catalog import EventType
from notifications.models import Notification, NotificationDeliveryAttempt
from notifications.services import NotificationEngineService, ProviderResult, normalize_phone
from notifications.tasks import queue_sms_event, send_sms_task
from users.models import User


class NotificationProviderTests(TestCase):
    def test_phone_normalization_is_kenya_scoped(self):
        self.assertEqual(normalize_phone('0711 223 344'), '+254711223344')

    @override_settings(NOTIFICATION_PROVIDER='console')
    @patch('notifications.services.requests.post')
    def test_safe_provider_never_contacts_external_gateway(self, mocked_post):
        result = NotificationEngineService.deliver_sms('+254711223344', 'Test message')
        self.assertTrue(result.success)
        self.assertTrue(result.suppressed)
        mocked_post.assert_not_called()

    @override_settings(
        NOTIFICATION_PROVIDER='africastalking',
        AFRICASTALKING_USERNAME='sandbox', AFRICASTALKING_API_KEY='test-key',
        AFRICASTALKING_SENDER_ID='',
    )
    @patch('notifications.services.requests.post')
    def test_africas_talking_success_is_parsed_without_message_body_logging(self, mocked_post):
        mocked_post.return_value.ok = True
        mocked_post.return_value.status_code = 201
        mocked_post.return_value.json.return_value = {
            'SMSMessageData': {'Recipients': [{
                'status': 'Success', 'statusCode': 101,
                'messageId': 'AT-123', 'cost': 'KES 0.80',
            }]},
        }
        result = NotificationEngineService.deliver_sms('+254711223344', 'Private body')
        self.assertTrue(result.success)
        self.assertEqual(result.message_id, 'AT-123')
        self.assertNotIn('Private body', result.response_summary)
        self.assertEqual(mocked_post.call_count, 1)


class DurableNotificationTests(TestCase):
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
