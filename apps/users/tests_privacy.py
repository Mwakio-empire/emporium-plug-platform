import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from analytics.models import AuditLog
from users.models import PrivacyRequest, User
from users.privacy_services import PrivacyRequestReviewService


@override_settings(
    PRIVACY_CONTROLLER_NAME='Emporium Plug',
    PRIVACY_CONTACT_EMAIL='privacy@example.invalid',
    PRIVACY_NOTICE_APPROVED=True,
)
class PrivacyControlTests(TestCase):
    password = 'StrongPass2026!'

    def setUp(self):
        self.customer = User.objects.create_user(
            username='privacy-customer', phone_number='+254700700001',
            email='privacy.customer@example.invalid', password=self.password,
            role=User.Role.CUSTOMER,
        )
        self.other_customer = User.objects.create_user(
            username='other-customer', phone_number='+254700700002',
            email='other.customer@example.invalid', password=self.password,
            role=User.Role.CUSTOMER,
        )
        self.super_admin = User.objects.create_user(
            username='privacy-admin', phone_number='+254700700003',
            email='privacy.admin@example.invalid', password=self.password,
            role=User.Role.SUPER_ADMIN, is_staff=True, is_superuser=True,
        )

    def test_privacy_notice_is_public(self):
        response = self.client.get(reverse('accounts:privacy'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Emporium Plug')
        self.assertContains(response, 'essential first-party cookies only')

    def test_customer_has_profile_and_discoverable_deletion_request(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My account')
        self.assertContains(response, 'request_type=DELETION')

        deletion_page = self.client.get(
            reverse('accounts:privacy'), {'request_type': PrivacyRequest.RequestType.DELETION},
        )
        self.assertContains(deletion_page, 'value="DELETION" selected')

    def test_customer_can_update_name_and_change_is_audited(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('accounts:profile'), {
            'first_name': 'Updated', 'last_name': 'Customer',
        })
        self.assertRedirects(response, reverse('accounts:profile'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'Updated')
        self.assertTrue(AuditLog.objects.filter(
            user=self.customer,
            action_type=AuditLog.ActionTypes.IDENTITY_UPDATED,
        ).exists())

    def test_non_customer_cannot_open_customer_profile(self):
        self.client.force_login(self.super_admin)
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 403)

    def test_customer_request_requires_current_password_and_is_audited(self):
        self.client.force_login(self.customer)
        url = reverse('accounts:privacy-request')
        rejected = self.client.post(url, {
            'request_type': PrivacyRequest.RequestType.ACCESS,
            'details': 'Please provide my information.',
            'password': 'wrong-password',
        })
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(PrivacyRequest.objects.exists())

        accepted = self.client.post(url, {
            'request_type': PrivacyRequest.RequestType.ACCESS,
            'details': 'Please provide my information.',
            'password': self.password,
        })
        self.assertRedirects(accepted, reverse('accounts:privacy'))
        request_record = PrivacyRequest.objects.get()
        self.assertEqual(request_record.user, self.customer)
        self.assertTrue(AuditLog.objects.filter(
            user=self.customer,
            action_type=AuditLog.ActionTypes.PRIVACY_REQUEST,
        ).exists())

    def test_only_one_open_request_of_each_type_is_allowed(self):
        PrivacyRequest.objects.create(
            user=self.customer, request_type=PrivacyRequest.RequestType.ACCESS,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PrivacyRequest.objects.create(
                    user=self.customer,
                    request_type=PrivacyRequest.RequestType.ACCESS,
                )

    def test_export_requires_password_and_contains_no_credentials_or_other_user(self):
        self.client.force_login(self.customer)
        url = reverse('accounts:privacy-export')
        rejected = self.client.post(url, {'password': 'wrong-password'})
        self.assertRedirects(rejected, reverse('accounts:privacy'))
        self.assertFalse(AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.PRIVACY_DATA_EXPORT,
        ).exists())

        response = self.client.post(url, {'password': self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertIn('attachment;', response['Content-Disposition'])
        payload = json.loads(response.content)
        self.assertEqual(payload['account']['email'], self.customer.email)
        serialized = response.content.decode()
        self.assertNotIn(self.other_customer.email, serialized)
        self.assertNotIn(self.customer.password, serialized)
        self.assertNotIn('password', payload['account'])
        self.assertTrue(AuditLog.objects.filter(
            user=self.customer,
            action_type=AuditLog.ActionTypes.PRIVACY_DATA_EXPORT,
        ).exists())

    def test_staff_cannot_use_customer_export(self):
        self.client.force_login(self.super_admin)
        response = self.client.post(
            reverse('accounts:privacy-export'), {'password': self.password},
        )
        self.assertEqual(response.status_code, 403)

    def test_only_super_admin_can_resolve_and_reauthentication_is_required(self):
        request_record = PrivacyRequest.objects.create(
            user=self.customer, request_type=PrivacyRequest.RequestType.CORRECTION,
        )
        with self.assertRaises(ValidationError):
            PrivacyRequestReviewService.resolve(
                request_id=request_record.pk, actor=self.super_admin,
                password='wrong-password',
                outcome=PrivacyRequest.Status.COMPLETED,
                response_note='Identity details were corrected.',
            )
        resolved = PrivacyRequestReviewService.resolve(
            request_id=request_record.pk, actor=self.super_admin,
            password=self.password,
            outcome=PrivacyRequest.Status.COMPLETED,
            response_note='Identity details were corrected.',
        )
        self.assertEqual(resolved.handled_by, self.super_admin)
        self.assertIsNotNone(resolved.handled_at)
        with self.assertRaises(ValidationError):
            PrivacyRequestReviewService.resolve(
                request_id=request_record.pk, actor=self.super_admin,
                password=self.password,
                outcome=PrivacyRequest.Status.REJECTED,
                response_note='Attempted duplicate resolution.',
            )
