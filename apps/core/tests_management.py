from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch


User = get_user_model()


class UnifiedManagementTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Management S18', location='S18', offers_customer_pickup=True,
        )
        self.manager = User.objects.create_user(
            username='management_manager', phone_number='+254722111001',
            email='management.manager@example.com', password='StrongPass!234',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.customer = User.objects.create_user(
            username='management_customer', phone_number='+254722111002',
            email='management.customer@example.com', password='StrongPass!234',
        )
        self.superuser = User.objects.create_superuser(
            username='management_super', phone_number='+254722111003',
            email='management.super@example.com', password='StrongPass!234',
        )

    def test_manager_dashboard_renders_task_first_navigation(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('core:analytics_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Operations overview')
        self.assertContains(response, 'What needs attention')
        self.assertNotContains(response, 'Open system data')

    def test_superuser_dashboard_links_to_system_data(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('core:analytics_dashboard'))
        self.assertContains(response, reverse('admin:index'))
        self.assertContains(response, 'Open system data')

    def test_anonymous_admin_is_routed_through_staff_login(self):
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.headers['Location'])
        self.assertIn('next=%2Fadmin%2F', response.headers['Location'])

    def test_customer_session_cannot_reach_admin_login_or_index(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:login'), {
            'username': self.superuser.username,
            'password': 'StrongPass!234',
        }).status_code, 403)

    def test_system_data_links_back_to_operations(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('core:analytics_dashboard'))
        self.assertContains(response, 'System data')

    def test_super_admin_storefront_has_visible_admin_entry(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse('core:storefront_home'))

        self.assertContains(response, 'aria-label="Open administration"')
        self.assertContains(response, reverse('core:analytics_dashboard'))

    def test_customer_storefront_does_not_expose_admin_entry(self):
        self.client.force_login(self.customer)

        response = self.client.get(reverse('core:storefront_home'))

        self.assertNotContains(response, 'aria-label="Open administration"')
