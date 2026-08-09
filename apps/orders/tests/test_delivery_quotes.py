from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from branches.models import Branch
from catalog.constants import STOREFRONT_SELECTED_BRANCH_KEY
from catalog.models import Category, Product
from inventory.models import Stock, StockAuditLog
from logistics.fulfilment_services import FulfilmentService
from logistics.models import KenyaCounty, KenyaTown
from orders.delivery_quote_access import (
    issue_delivery_quote_token,
    resolve_delivery_quote_token,
)
from orders.delivery_quote_services import DeliveryQuoteService
from orders.models import (
    DeliveryQuoteClosure, DeliveryQuoteRequest, DeliveryQuoteStatusHistory, Order,
)
from orders.tasks import expire_delivery_quotes
from users.models import User


NAIROBI = ZoneInfo('Africa/Nairobi')


class DeliveryQuoteLifecycleTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Quote S18', location='Gaberone Plaza', offers_customer_pickup=True,
        )
        self.manager = User.objects.create_user(
            username='quote_manager', phone_number='+254711222333',
            email='quote-manager@example.com', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.quote = DeliveryQuoteRequest.objects.create(
            branch=self.branch,
            customer_phone='+254712345678',
            customer_name='Amina Customer',
            customer_email='amina@example.com',
            county='Kakamega',
            town='Kakamega',
            preferred_collection_area='Main town stage',
            cart_snapshot=[{
                'type': 'product', 'id': 12, 'name': 'Cooking pot',
                'quantity': 2, 'display_unit_price': '1200.00',
            }],
            requested_subtotal=Decimal('2400.00'),
            response_due_at=datetime(2026, 8, 3, 8, 30, tzinfo=NAIROBI),
        )

    def test_response_deadline_rolls_saturday_evening_into_monday(self):
        saturday = datetime(2026, 8, 1, 17, 50, tzinfo=NAIROBI)

        due = DeliveryQuoteService.response_due_at(saturday)

        self.assertEqual(due, datetime(2026, 8, 3, 8, 20, tzinfo=NAIROBI))

    def test_response_deadline_skips_configured_public_holiday(self):
        DeliveryQuoteClosure.objects.create(
            date=date(2026, 8, 3), label='Client-approved closure',
        )
        saturday = datetime(2026, 8, 1, 17, 50, tzinfo=NAIROBI)

        due = DeliveryQuoteService.response_due_at(saturday)

        self.assertEqual(due, datetime(2026, 8, 4, 8, 20, tzinfo=NAIROBI))

    def test_publish_starts_fixed_twenty_four_hour_validity_window(self):
        now = datetime(2026, 8, 3, 9, 0, tzinfo=NAIROBI)

        published = DeliveryQuoteService.publish(
            quote=self.quote,
            staff=self.manager,
            transport_operator='Kakamega Shuttle',
            collection_point='Kakamega main parcel office',
            delivery_fee=Decimal('350.00'),
            expected_arrival='Next working day, 2:00 PM to 5:00 PM',
            now=now,
        )

        self.assertEqual(published.status, DeliveryQuoteRequest.Status.QUOTED)
        self.assertEqual(published.quoted_at, now)
        self.assertEqual(published.expires_at, now + timedelta(hours=24))
        self.assertEqual(published.delivery_fee, Decimal('350.00'))
        history = DeliveryQuoteStatusHistory.objects.get(quote=published)
        self.assertEqual(history.old_status, DeliveryQuoteRequest.Status.REQUESTED)
        self.assertEqual(history.new_status, DeliveryQuoteRequest.Status.QUOTED)
        self.assertEqual(history.changed_by, self.manager)

    def test_declined_quote_cannot_be_published(self):
        self.quote.status = DeliveryQuoteRequest.Status.DECLINED
        self.quote.declined_at = datetime(2026, 8, 3, 9, 0, tzinfo=NAIROBI)
        self.quote.save(update_fields=['status', 'declined_at'])

        with self.assertRaisesMessage(ValidationError, 'cannot be published'):
            DeliveryQuoteService.publish(
                quote=self.quote,
                staff=self.manager,
                transport_operator='Kakamega Shuttle',
                collection_point='Kakamega main parcel office',
                delivery_fee=Decimal('350.00'),
                expected_arrival='Tomorrow afternoon',
            )

    def test_inventory_manager_cannot_publish_commercial_quote_terms(self):
        inventory_manager = User.objects.create_user(
            username='quote_inventory_only', phone_number='+254711222334',
            email='quote-inventory-only@example.com', password='StrongPass123!',
            role=User.Role.INVENTORY_MANAGER, branch=self.branch,
        )

        with self.assertRaisesMessage(ValidationError, 'branch manager or super admin'):
            DeliveryQuoteService.publish(
                quote=self.quote,
                staff=inventory_manager,
                transport_operator='Kakamega Shuttle',
                collection_point='Kakamega main parcel office',
                delivery_fee=Decimal('350.00'),
                expected_arrival='Tomorrow afternoon',
            )

    def test_signed_guest_token_resolves_only_its_quote(self):
        token = issue_delivery_quote_token(self.quote)

        resolved = resolve_delivery_quote_token(token)

        self.assertEqual(resolved, self.quote)
        self.assertIsNone(resolve_delivery_quote_token(token + 'tampered'))

    @patch('notifications.tasks.send_delivery_quote_ready_email.delay')
    @patch('notifications.tasks.send_delivery_quote_ready_sms.delay')
    def test_publish_queues_customer_notifications_after_commit(self, sms_delay, email_delay):
        with self.captureOnCommitCallbacks(execute=True):
            DeliveryQuoteService.publish(
                quote=self.quote,
                staff=self.manager,
                transport_operator='Kakamega Shuttle',
                collection_point='Kakamega main parcel office',
                delivery_fee=Decimal('350.00'),
                expected_arrival='Tomorrow afternoon',
            )

        sms_delay.assert_called_once_with(str(self.quote.pk))
        email_delay.assert_called_once_with(str(self.quote.pk))

    def test_expiry_sweep_changes_only_overdue_published_quotes(self):
        self.quote.status = DeliveryQuoteRequest.Status.QUOTED
        self.quote.quoted_at = timezone.now() - timedelta(hours=25)
        self.quote.expires_at = timezone.now() - timedelta(hours=1)
        self.quote.save(update_fields=['status', 'quoted_at', 'expires_at'])

        expired = expire_delivery_quotes()

        self.assertEqual(expired, 1)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, DeliveryQuoteRequest.Status.EXPIRED)
        self.assertEqual(Order.objects.count(), 0)


class DeliveryQuoteAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.branch = Branch.objects.create(
            name='API Quote S18', location='Gaberone Plaza', offers_customer_pickup=True,
        )
        self.customer = User.objects.create_user(
            username='quote_customer', phone_number='+254722333444',
            email='quote-customer@example.com', password='StrongPass123!',
            role=User.Role.CUSTOMER,
        )
        self.other_customer = User.objects.create_user(
            username='other_quote_customer', phone_number='+254722333445',
            email='other-quote@example.com', password='StrongPass123!',
            role=User.Role.CUSTOMER,
        )
        self.manager = User.objects.create_user(
            username='api_quote_manager', phone_number='+254722333446',
            email='api-quote-manager@example.com', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        category = Category.objects.create(name='Quote products', slug='quote-products')
        self.product = Product.objects.create(
            name='Quoted cooking pot', slug='quoted-cooking-pot', category=category,
            price=Decimal('1200.00'), status=Product.Status.ACTIVE,
        )
        self.stock = Stock.objects.create(branch=self.branch, product=self.product, quantity=8)
        self.kakamega_county = KenyaCounty.objects.get(code='37')
        self.kakamega_town = KenyaTown.objects.get(
            county=self.kakamega_county,
            normalized_name='kakamega',
        )
        self.kisumu_county = KenyaCounty.objects.get(code='42')
        self.kisumu_town = KenyaTown.objects.get(
            county=self.kisumu_county,
            normalized_name='kisumu',
        )
        session = self.client.session
        session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch.pk
        session.save()

    def _add_cart_item(self):
        return self.client.post(
            reverse('cart:add'),
            {'type': 'product', 'id': self.product.pk, 'quantity': 2},
            format='json',
        )

    def _payload(self):
        return {
            'customer_name': 'Amina Customer',
            'customer_phone': '0712 345 678',
            'customer_email': 'amina@example.com',
            'county_code': self.kakamega_county.code,
            'town_id': self.kakamega_town.pk,
            'use_custom_town': False,
            'custom_town': '',
            'preferred_collection_area': 'Main town stage',
            'notes': 'Call before dispatch.',
        }

    def _assert_no_quote_side_effects(self):
        self.assertEqual(DeliveryQuoteRequest.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StockAuditLog.objects.count(), 0)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 8)
        self.assertEqual(self.stock.reserved_quantity, 0)

    def _create_published_guest_quote(self):
        self._add_cart_item()
        created = self.client.post(
            reverse('checkout:delivery-quote-create'), self._payload(), format='json',
        )
        quote = DeliveryQuoteRequest.objects.get(reference=created.data['reference'])
        DeliveryQuoteService.publish(
            quote=quote,
            staff=self.manager,
            transport_operator='Kakamega Shuttle',
            collection_point='Kakamega main parcel office',
            delivery_fee=Decimal('350.00'),
            expected_arrival='Next working day, 2:00 PM to 5:00 PM',
        )
        return quote, created.data['access_token']

    def test_guest_request_captures_snapshot_without_order_or_stock_reservation(self):
        self._add_cart_item()

        response = self.client.post(
            reverse('checkout:delivery-quote-create'), self._payload(), format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Order.objects.count(), 0)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 0)
        quote = DeliveryQuoteRequest.objects.get(reference=response.data['reference'])
        self.assertEqual(quote.county, self.kakamega_county.name)
        self.assertEqual(quote.town, self.kakamega_town.name)
        self.assertEqual(quote.requested_subtotal, Decimal('2400.00'))
        self.assertEqual(quote.cart_snapshot[0]['product_id'], self.product.pk)
        self.assertIn('access_token', response.data)

    def test_guest_can_request_quote_for_explicit_unlisted_town(self):
        self._add_cart_item()
        payload = self._payload()
        payload.update({
            'town_id': None,
            'use_custom_town': True,
            'custom_town': '  Shinyalu   Centre  ',
        })

        response = self.client.post(
            reverse('checkout:delivery-quote-create'), payload, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        quote = DeliveryQuoteRequest.objects.get(reference=response.data['reference'])
        self.assertEqual(quote.county, self.kakamega_county.name)
        self.assertEqual(quote.town, 'Shinyalu Centre')
        self.assertEqual(Order.objects.count(), 0)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 0)

    def test_structured_destination_rejections_have_no_quote_order_or_stock_side_effects(self):
        self._add_cart_item()
        inactive_town = KenyaTown.objects.create(
            county=self.kakamega_county,
            name='Inactive Centre',
            is_active=False,
            source='TEST',
            source_revision='TEST',
        )
        cases = (
            (
                'cross-county town',
                {'town_id': self.kisumu_town.pk},
                'selected county',
            ),
            (
                'inactive town',
                {'town_id': inactive_town.pk},
                'active town',
            ),
            (
                'tampered town identifier',
                {'town_id': 'not-a-town-id'},
                'active town',
            ),
            (
                'missing town selection',
                {'town_id': None},
                'choose a town',
            ),
            (
                'missing county',
                {'county_code': ''},
                'active kenyan county',
            ),
        )

        for label, changes, expected_error in cases:
            with self.subTest(label=label):
                payload = self._payload()
                payload.update(changes)
                response = self.client.post(
                    reverse('checkout:delivery-quote-create'), payload, format='json',
                )
                self.assertEqual(
                    response.status_code, status.HTTP_400_BAD_REQUEST, response.data,
                )
                self.assertIn(expected_error, response.data['error'].lower())
                self._assert_no_quote_side_effects()

    def test_inactive_county_is_rejected_before_quote_write(self):
        self._add_cart_item()
        self.kakamega_county.is_active = False
        self.kakamega_county.save(update_fields=['is_active'])

        response = self.client.post(
            reverse('checkout:delivery-quote-create'), self._payload(), format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('active kenyan county', response.data['error'].lower())
        self._assert_no_quote_side_effects()

    def test_legacy_free_text_county_and_town_cannot_bypass_structured_validation(self):
        self._add_cart_item()
        payload = self._payload()
        payload.pop('county_code')
        payload.pop('town_id')
        payload.update({'county': 'Kakamega', 'town': 'Kakamega'})

        response = self.client.post(
            reverse('checkout:delivery-quote-create'), payload, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('active kenyan county', response.data['error'].lower())
        self._assert_no_quote_side_effects()

    def test_empty_cart_cannot_request_delivery_quote(self):
        response = self.client.post(
            reverse('checkout:delivery-quote-create'), self._payload(), format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cart is empty', response.data['error'].lower())

    def test_guest_status_requires_its_signed_token(self):
        self._add_cart_item()
        created = self.client.post(
            reverse('checkout:delivery-quote-create'), self._payload(), format='json',
        )

        denied = self.client.get(
            reverse('orders:delivery-quote-status', args=[created.data['reference']]),
        )
        allowed = self.client.get(
            reverse('orders:delivery-quote-status', args=[created.data['reference']]),
            HTTP_X_DELIVERY_QUOTE_TOKEN=created.data['access_token'],
        )

        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed.data['status'], DeliveryQuoteRequest.Status.REQUESTED)
        self.assertEqual(allowed.data['town'], self.kakamega_town.name)

    def test_authenticated_customer_cannot_read_another_customers_quote(self):
        self.client.force_authenticate(self.customer)
        self._add_cart_item()
        created = self.client.post(
            reverse('checkout:delivery-quote-create'), self._payload(), format='json',
        )
        self.client.force_authenticate(self.other_customer)

        response = self.client.get(
            reverse('orders:delivery-quote-status', args=[created.data['reference']]),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_acceptance_requires_confirmation_of_current_total(self):
        quote, token = self._create_published_guest_quote()
        self.product.price = Decimal('1300.00')
        self.product.save(update_fields=['price'])
        url = reverse('orders:delivery-quote-accept', args=[quote.reference])

        preview = self.client.post(
            url, {'preview_only': True}, format='json',
            HTTP_X_DELIVERY_QUOTE_TOKEN=token,
        )
        stale = self.client.post(
            url, {'confirmed': True, 'expected_total': '2750.00'}, format='json',
            HTTP_X_DELIVERY_QUOTE_TOKEN=token,
        )

        self.assertEqual(preview.status_code, status.HTTP_200_OK, preview.data)
        self.assertEqual(preview.data['subtotal'], '2600.00')
        self.assertEqual(preview.data['delivery_fee'], '350.00')
        self.assertEqual(preview.data['total_payable'], '2950.00')
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(stale.data['requires_confirmation'])
        self.assertEqual(Order.objects.count(), 0)

    def test_acceptance_creates_one_prepaid_parcel_order_and_reserves_once(self):
        quote, token = self._create_published_guest_quote()
        url = reverse('orders:delivery-quote-accept', args=[quote.reference])
        payload = {'confirmed': True, 'expected_total': '2750.00'}

        first = self.client.post(
            url, payload, format='json', HTTP_X_DELIVERY_QUOTE_TOKEN=token,
        )
        second = self.client.post(
            url, payload, format='json', HTTP_X_DELIVERY_QUOTE_TOKEN=token,
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual(first.data['order_number'], second.data['order_number'])
        order = Order.objects.get(order_number=first.data['order_number'])
        self.assertEqual(order.order_type, Order.OrderType.ONLINE_DELIVERY)
        self.assertEqual(order.payment_method, Order.PaymentMethod.MPESA_STK)
        self.assertEqual(order.delivery_fee, Decimal('350.00'))
        self.assertEqual(order.total_payable, Decimal('2750.00'))
        self.assertEqual(order.parcel_town, self.kakamega_town.name)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 2)
        quote.refresh_from_db()
        self.assertEqual(quote.status, DeliveryQuoteRequest.Status.ACCEPTED)
        self.assertEqual(quote.order, order)

    def test_expired_quote_cannot_create_order(self):
        quote, token = self._create_published_guest_quote()
        quote.expires_at = timezone.now() - timedelta(seconds=1)
        quote.save(update_fields=['expires_at'])

        response = self.client.post(
            reverse('orders:delivery-quote-accept', args=[quote.reference]),
            {'confirmed': True, 'expected_total': '2750.00'}, format='json',
            HTTP_X_DELIVERY_QUOTE_TOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Order.objects.count(), 0)

    def test_customer_can_decline_without_creating_order_or_reserving_stock(self):
        quote, token = self._create_published_guest_quote()

        response = self.client.post(
            reverse('orders:delivery-quote-decline', args=[quote.reference]),
            {'confirmed': True}, format='json',
            HTTP_X_DELIVERY_QUOTE_TOKEN=token,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        quote.refresh_from_db()
        self.assertEqual(quote.status, DeliveryQuoteRequest.Status.DECLINED)
        self.assertEqual(Order.objects.count(), 0)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 0)

    def test_accepted_quote_order_uses_parcel_dispatch_workflow(self):
        quote, token = self._create_published_guest_quote()
        accepted = self.client.post(
            reverse('orders:delivery-quote-accept', args=[quote.reference]),
            {'confirmed': True, 'expected_total': '2750.00'}, format='json',
            HTTP_X_DELIVERY_QUOTE_TOKEN=token,
        )
        order = Order.objects.get(order_number=accepted.data['order_number'])
        order.status = Order.Status.PACKED
        order.save(update_fields=['status'])

        dispatch, dispatched_order = FulfilmentService.dispatch_parcel(
            order_id=order.pk,
            actor=self.manager,
            parcel_reference='KAKA-001',
            actual_transport_cost='300.00',
        )

        self.assertEqual(dispatch.order, order)
        self.assertEqual(dispatched_order.status, Order.Status.DISPATCHED)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.reserved_quantity, 0)
        self.assertEqual(self.stock.quantity, 6)


class DeliveryQuoteStaffWorkspaceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Staff Quote S18', location='Gaberone Plaza')
        self.other_branch = Branch.objects.create(name='Staff Quote OTC', location='OTC Mall')
        self.manager = User.objects.create_user(
            username='staff_quote_manager', phone_number='+254733444555',
            email='staff-quote-manager@example.com', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.inventory_manager = User.objects.create_user(
            username='quote_inventory_manager', phone_number='+254733444556',
            email='quote-inventory@example.com', password='StrongPass123!',
            role=User.Role.INVENTORY_MANAGER, branch=self.branch,
        )
        self.quote = DeliveryQuoteRequest.objects.create(
            branch=self.branch, customer_phone='+254712345678', customer_name='Amina',
            county='Kakamega', town='Kakamega', preferred_collection_area='Main stage',
            cart_snapshot=[], requested_subtotal=Decimal('2400.00'),
            response_due_at=datetime(2026, 8, 3, 8, 30, tzinfo=NAIROBI),
        )
        self.other_quote = DeliveryQuoteRequest.objects.create(
            branch=self.other_branch, customer_phone='+254712345679', customer_name='Brian',
            county='Kisumu', town='Kisumu', preferred_collection_area='Bus park',
            cart_snapshot=[], requested_subtotal=Decimal('1800.00'),
            response_due_at=datetime(2026, 8, 3, 8, 30, tzinfo=NAIROBI),
        )
        self.client.force_login(self.manager)

    def test_workspace_is_branch_scoped(self):
        response = self.client.get(reverse('delivery-quote-workspace'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Operations navigation')
        self.assertContains(response, self.quote.reference)
        self.assertNotContains(response, self.other_quote.reference)

    def test_inventory_manager_cannot_access_customer_quote_workspace(self):
        self.client.force_login(self.inventory_manager)

        response = self.client.get(reverse('delivery-quote-workspace'))

        self.assertEqual(response.status_code, 403)

    def test_manager_can_publish_complete_quote(self):
        response = self.client.post(
            reverse('delivery-quote-detail', args=[self.quote.reference]),
            {
                'action': 'publish',
                'transport_operator': 'Kakamega Shuttle',
                'collection_point': 'Kakamega main parcel office',
                'delivery_fee': '350.00',
                'expected_arrival': 'Next working day, 2:00 PM to 5:00 PM',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, DeliveryQuoteRequest.Status.QUOTED)
        self.assertEqual(self.quote.reviewed_by, self.manager)
        self.assertContains(response, 'Quote published')

    def test_manager_cannot_open_another_branch_quote(self):
        response = self.client.get(
            reverse('delivery-quote-detail', args=[self.other_quote.reference]),
        )

        self.assertEqual(response.status_code, 404)


class DeliveryQuoteCustomerPageTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Page Quote S18', location='Gaberone Plaza', offers_customer_pickup=True,
        )
        category = Category.objects.create(name='Page products', slug='page-products')
        self.product = Product.objects.create(
            name='Page cooking pot', slug='page-cooking-pot', category=category,
            price=Decimal('1200.00'), status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch, product=self.product, quantity=8)
        session = self.client.session
        session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch.pk
        session.save()
        self.client.post(
            reverse('cart:add'),
            data='{"type":"product","id":"%s","quantity":1}' % self.product.pk,
            content_type='application/json',
        )

    def test_checkout_offers_structured_quote_and_keeps_pickup_selected(self):
        response = self.client.get(reverse('checkout-page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Request a delivery quote')
        self.assertContains(response, 'Monday–Saturday, 8:00 AM–6:00 PM')
        self.assertContains(
            response,
            'name="fulfilment_choice" value="PICKUP" required checked',
            html=False,
        )

    def test_public_status_page_is_a_protected_data_shell(self):
        response = self.client.get(
            reverse('delivery-quote-page', args=['EPQ-DOESNOTEXIST']),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Checking your delivery quote')
        self.assertNotContains(response, 'Amina Customer')
