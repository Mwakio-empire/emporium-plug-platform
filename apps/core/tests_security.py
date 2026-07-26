from django.test import TestCase
from django.urls import reverse

from users.models import User


class SecurityBoundaryTests(TestCase):
    def test_legitimate_search_language_is_not_blocked_by_regex_firewall(self):
        response = self.client.get(reverse('core:storefront_home'), {
            'q': 'select shoes from the new catalogue',
        })
        self.assertEqual(response.status_code, 200)

    def test_public_response_has_enforced_csp_and_browser_hardening(self):
        response = self.client.get(reverse('core:storefront_home'))
        self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])
        self.assertIn("object-src 'none'", response.headers['Content-Security-Policy'])
        self.assertEqual(
            response.headers['Permissions-Policy'],
            'camera=(), microphone=(), geolocation=(), payment=()',
        )
        self.assertEqual(response.headers['X-Permitted-Cross-Domain-Policies'], 'none')

    def test_authenticated_response_is_private_and_not_stored(self):
        user = User.objects.create_user(
            username='security-cache-customer', phone_number='+254700888111',
            email='security.cache@test.invalid', password='StrongPass2026!',
            role=User.Role.CUSTOMER,
        )
        self.client.force_login(user)
        response = self.client.get(reverse('core:storefront_home'))
        cache_control = response.headers['Cache-Control']
        self.assertIn('private', cache_control)
        self.assertIn('no-store', cache_control)

    def test_anonymous_user_cannot_trigger_sentry_diagnostic(self):
        response = self.client.get(reverse('core:sentry_trigger'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.headers['Location'])

    def test_authenticated_non_admin_cannot_trigger_sentry_diagnostic(self):
        user = User.objects.create_user(
            username='security-diagnostic-customer', phone_number='+254700888112',
            email='security.diagnostic@test.invalid', password='StrongPass2026!',
            role=User.Role.CUSTOMER,
        )
        self.client.force_login(user)
        response = self.client.get(reverse('core:sentry_trigger'))
        self.assertEqual(response.status_code, 403)
