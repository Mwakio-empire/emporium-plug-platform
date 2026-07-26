
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from unittest.mock import patch
from branches.models import Branch
from catalog.models import Category, Product
from orders.models import Order, OrderItem
from logistics.models import DeliveryAssignment, RiderProfile
User = get_user_model()
class InboundSMSWebhookTestDataMixin:
    def setUp(self):
        self.branch = Branch.objects.create(name="Inbound SMS Branch", location="Test")
        self.customer = User.objects.create_user(
            username='inboundsmscust0001', phone_number='+254788300001',
            email='inboundsmscust0001@test.com', password='CustPass123!',
            role=User.Role.CUSTOMER,
        )
        self.rider_user = User.objects.create_user(
            username='inboundsmsrider0001', phone_number='+254788300002',
            email='inboundsmsrider0001@test.com', password='RiderPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        self.rider_profile = RiderProfile.objects.create(user=self.rider_user, branch=self.branch)
        self.category = Category.objects.create(name="Inbound SMS Category", slug="inbound-sms-category")
        self.product = Product.objects.create(
            name="Inbound SMS Product", slug="inbound-sms-product",
            category=self.category, price=Decimal("1000.00"), status=Product.Status.ACTIVE,
        )
    def _delivered_assignment(self, phone):
        order = Order.objects.create(
            branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_DELIVERY,
            customer_phone=phone,
            payment_method=Order.PaymentMethod.MPESA_STK,
            status=Order.Status.DELIVERED,
            processed_by=self.customer,
            subtotal=Decimal('1000.00'), total_payable=Decimal('1000.00'),
        )
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'))
        assignment = DeliveryAssignment.objects.create(
            order=order, rider=self.rider_profile,
            status=DeliveryAssignment.DeliveryStatus.DELIVERED,
            completed_at=timezone.now(),
        )
        return order, assignment
WEBHOOK_TOKEN = 'phase-12-inbound-sms-test-token-000000000000'


@override_settings(
    INBOUND_SMS_ENABLED=True,
    INBOUND_SMS_WEBHOOK_TOKEN=WEBHOOK_TOKEN,
)
class InboundSMSWebhookTests(InboundSMSWebhookTestDataMixin, TestCase):
    def _post(self, data, **extra):
        return self.client.post(
            reverse('notifications:sms_inbound'), data,
            HTTP_X_WEBHOOK_TOKEN=WEBHOOK_TOKEN,
            **extra,
        )

    def test_missing_or_incorrect_secret_is_rejected_without_mutation(self):
        _, assignment = self._delivered_assignment(phone='+254788400099')
        url = reverse('notifications:sms_inbound')
        self.assertEqual(self.client.post(url, {'from': '+254788400099', 'text': 'YES'}).status_code, 404)
        self.assertEqual(self.client.post(
            url, {'from': '+254788400099', 'text': 'YES'},
            HTTP_X_WEBHOOK_TOKEN='wrong',
        ).status_code, 404)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.customer_confirmed_at)

    def test_missing_from_field_returns_200(self):
        response = self._post({'text': 'YES'})
        self.assertEqual(response.status_code, 200)
    def test_yes_reply_confirms_delivery(self):
        order, assignment = self._delivered_assignment(phone='+254788400010')
        response = self._post({
            'from': '+254788400010', 'text': 'YES',
        })
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertIsNotNone(assignment.customer_confirmed_at)
        self.assertFalse(assignment.customer_disputed)
    def test_yes_reply_case_insensitive_with_trailing_text(self):
        order, assignment = self._delivered_assignment(phone='+254788400011')
        self._post({'from': '+254788400011', 'text': 'yes thanks'})
        assignment.refresh_from_db()
        self.assertIsNotNone(assignment.customer_confirmed_at)
    @patch('notifications.tasks.send_delivery_dispute_manager_alert.delay')
    def test_non_yes_reply_disputes_and_alerts_manager(self, mock_alert):
        order, assignment = self._delivered_assignment(phone='+254788400012')
        response = self._post({
            'from': '+254788400012', 'text': 'I never got my order',
        })
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertTrue(assignment.customer_disputed)
        self.assertIn('never got', assignment.dispute_note)
        self.assertIsNone(assignment.customer_confirmed_at)
        mock_alert.assert_called_once()
    def test_local_phone_format_normalized_and_matched(self):
        order, assignment = self._delivered_assignment(phone='+254788400013')
        self._post({'from': '0788400013', 'text': 'YES'})
        assignment.refresh_from_db()
        self.assertIsNotNone(assignment.customer_confirmed_at)
    def test_no_matching_delivery_does_not_crash(self):
        response = self._post({
            'from': '+254700999999', 'text': 'YES',
        })
        self.assertEqual(response.status_code, 200)
    def test_picks_most_recent_delivery_when_multiple_exist(self):
        order1, assignment1 = self._delivered_assignment(phone='+254788400015')
        assignment1.completed_at = timezone.now() - timezone.timedelta(days=1)
        assignment1.save(update_fields=['completed_at'])
        order2, assignment2 = self._delivered_assignment(phone='+254788400015')
        self._post({'from': '+254788400015', 'text': 'YES'})
        assignment1.refresh_from_db()
        assignment2.refresh_from_db()
        self.assertIsNone(assignment1.customer_confirmed_at)
        self.assertIsNotNone(assignment2.customer_confirmed_at)


class DisabledInboundSMSWebhookTests(TestCase):
    @override_settings(INBOUND_SMS_ENABLED=False)
    def test_disabled_endpoint_is_not_exposed(self):
        response = self.client.post(reverse('notifications:sms_inbound'), {
            'from': '+254788400010', 'text': 'YES',
        })
        self.assertEqual(response.status_code, 404)
