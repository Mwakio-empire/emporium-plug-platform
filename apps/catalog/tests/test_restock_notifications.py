from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from inventory.models import Stock
from notifications.models import Notification

from catalog.models import Category, Product, ProductVariant, RestockSubscription
from catalog.tasks import send_customer_restock_alerts


User = get_user_model()


class RestockSubscriptionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.category = Category.objects.create(
            name='Restock test category', slug='restock-test-category',
        )
        self.branch = Branch.objects.create(
            name='Restock test S18', location='Nairobi',
        )
        self.product = Product.objects.create(
            name='Restock test kettle', slug='restock-test-kettle',
            sku='RESTOCK-KETTLE', category=self.category,
            price=Decimal('1200.00'), status=Product.Status.ACTIVE,
        )
        self.stock = Stock.objects.create(
            branch=self.branch, product=self.product, quantity=0,
        )
        self.subscribe_url = reverse('core:restock_subscribe')

    def test_guest_can_request_one_normalized_sms_alert(self):
        response = self.client.post(self.subscribe_url, {
            'product_id': self.product.pk,
            'phone_number': '0714 819 427',
            'next': reverse('core:product_detail', kwargs={'slug': self.product.slug}),
        })

        self.assertRedirects(
            response, reverse('core:product_detail', kwargs={'slug': self.product.slug}),
        )
        subscription = RestockSubscription.objects.get()
        self.assertEqual(subscription.phone_number, '+254714819427')
        self.assertEqual(subscription.product, self.product)
        self.assertIsNone(subscription.variant)
        self.assertEqual(subscription.status, RestockSubscription.Status.ACTIVE)

        self.client.post(self.subscribe_url, {
            'product_id': self.product.pk,
            'phone_number': '+254714819427',
        })
        self.assertEqual(RestockSubscription.objects.count(), 1)

    def test_in_stock_item_does_not_accept_a_waitlist_request(self):
        self.stock.quantity = 1
        self.stock.save(update_fields=['quantity'])

        response = self.client.post(self.subscribe_url, {
            'product_id': self.product.pk,
            'phone_number': '+254714819427',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(RestockSubscription.objects.exists())
        follow_up = self.client.get(response.url)
        self.assertContains(follow_up, 'already available')

    def test_variant_subscription_tracks_the_exact_option(self):
        variant = ProductVariant.objects.create(
            product=self.product, sku='RESTOCK-KETTLE-BLACK',
            attribute_name='Colour', attribute_value='Black', is_active=True,
        )
        self.stock.delete()
        Stock.objects.create(branch=self.branch, variant=variant, quantity=0)

        self.client.post(self.subscribe_url, {
            'product_id': self.product.pk,
            'variant_id': variant.pk,
            'phone_number': '+254714819427',
        })

        subscription = RestockSubscription.objects.get()
        self.assertEqual(subscription.variant, variant)
        self.assertIsNone(subscription.product)

    def test_customer_is_linked_and_phone_is_prefilled_on_product_page(self):
        customer = User.objects.create_user(
            username='restock_customer', phone_number='+254700111333',
            email='restock@example.test', password='StrongPass123!',
        )
        self.client.force_login(customer)

        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': self.product.slug},
        ))

        self.assertContains(response, 'Notify me when available')
        self.assertContains(response, 'value="+254700111333"')
        self.client.post(self.subscribe_url, {
            'product_id': self.product.pk,
            'phone_number': customer.phone_number,
        })
        self.assertEqual(RestockSubscription.objects.get().customer, customer)

    def test_customer_can_cancel_with_opaque_token(self):
        subscription = RestockSubscription.objects.create_for_target(
            product=self.product, phone_number='+254714819427',
        )
        url = reverse('core:restock_cancel', kwargs={'token': subscription.unsubscribe_token})

        self.assertContains(self.client.get(url), self.product.name)
        response = self.client.post(url)

        self.assertRedirects(
            response, reverse('core:product_detail', kwargs={'slug': self.product.slug}),
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, RestockSubscription.Status.CANCELLED)
        self.assertIsNotNone(subscription.cancelled_at)

    def test_active_alert_replaces_the_subscription_form(self):
        self.client.post(self.subscribe_url, {
            'product_id': self.product.pk,
            'phone_number': '+254714819427',
            'next': reverse('core:product_detail', kwargs={'slug': self.product.slug}),
        })

        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': self.product.slug},
        ))

        self.assertContains(response, 'Your restock alert is active.')
        self.assertContains(response, 'Manage or cancel alert')
        self.assertNotContains(response, 'Notify me when available')

    def test_repeated_requests_are_rate_limited_without_exposing_the_phone(self):
        payload = {
            'product_id': self.product.pk,
            'phone_number': '+254714819427',
        }
        for _ in range(5):
            self.client.post(self.subscribe_url, payload)

        response = self.client.post(self.subscribe_url, payload, follow=True)

        self.assertContains(response, 'Too many attempts')
        self.assertNotContains(response, '+254714819427')
        self.assertEqual(RestockSubscription.objects.count(), 1)


class RestockAlertTaskTests(TestCase):
    def setUp(self):
        category = Category.objects.create(
            name='Restock task category', slug='restock-task-category',
        )
        branch = Branch.objects.create(name='Restock task S18', location='Nairobi')
        self.product = Product.objects.create(
            name='Restocked pan', slug='restocked-pan', sku='RESTOCK-PAN',
            category=category, price=Decimal('900.00'), status=Product.Status.ACTIVE,
        )
        self.stock = Stock.objects.create(branch=branch, product=self.product, quantity=0)
        self.subscription = RestockSubscription.objects.create_for_target(
            product=self.product, phone_number='+254714819427',
        )

    @patch('catalog.tasks.queue_sms_event', return_value=True)
    def test_alert_is_queued_once_after_sellable_stock_returns(self, queue_sms):
        self.stock.quantity = 2
        self.stock.save(update_fields=['quantity'])

        first = send_customer_restock_alerts()
        second = send_customer_restock_alerts()

        self.subscription.refresh_from_db()
        self.assertEqual(first, {'notified': 1, 'expired': 0})
        self.assertEqual(second, {'notified': 0, 'expired': 0})
        self.assertEqual(self.subscription.status, RestockSubscription.Status.NOTIFIED)
        self.assertIsNotNone(self.subscription.notified_at)
        queue_sms.assert_called_once()

    @patch('catalog.tasks.queue_sms_event')
    def test_expired_subscription_is_closed_without_an_alert(self, queue_sms):
        RestockSubscription.objects.filter(pk=self.subscription.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.stock.quantity = 2
        self.stock.save(update_fields=['quantity'])

        result = send_customer_restock_alerts()

        self.subscription.refresh_from_db()
        self.assertEqual(result, {'notified': 0, 'expired': 1})
        self.assertEqual(self.subscription.status, RestockSubscription.Status.EXPIRED)
        queue_sms.assert_not_called()

    @patch('notifications.tasks.send_sms_task.delay')
    def test_delivery_job_runs_only_after_durable_event_commits(self, send_delay):
        self.stock.quantity = 2
        self.stock.save(update_fields=['quantity'])

        with self.captureOnCommitCallbacks(execute=True):
            result = send_customer_restock_alerts()

        self.assertEqual(result['notified'], 1)
        notification = Notification.objects.get()
        self.assertEqual(notification.event_type, 'BACK_IN_STOCK')
        self.assertEqual(notification.reference_id, str(self.subscription.pk))
        send_delay.assert_called_once()
