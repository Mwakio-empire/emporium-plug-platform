from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from logistics.fulfilment_services import FulfilmentService, add_working_days
from logistics.models import DeliveryAssignment, PackingChecklist, RiderProfile
from orders.models import Order, OrderItem
from users.models import User


class Phase8FulfilmentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.s18 = Branch.objects.create(
            name='Gaberone Plaza S18', location='Second floor, Gaberone Plaza',
            offers_customer_pickup=True,
        )
        self.b03 = Branch.objects.create(
            name='Gaberone Plaza B03', location='Gaberone Plaza',
        )
        self.manager = User.objects.create_user(
            username='phase8manager', phone_number='+254733810001',
            email='phase8.manager@example.test', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.s18,
        )
        self.staff = User.objects.create_user(
            username='phase8staff', phone_number='+254733810002',
            email='phase8.staff@example.test', password='StrongPass123!',
            role=User.Role.STAFF, branch=self.s18,
        )
        self.customer = User.objects.create_user(
            username='phase8customer', phone_number='+254733810003',
            email='phase8.customer@example.test', password='StrongPass123!',
            role=User.Role.CUSTOMER,
        )
        rider_user = User.objects.create_user(
            username='phase8rider', phone_number='+254733810004',
            email='phase8.rider@example.test', password='StrongPass123!',
            role=User.Role.STAFF, branch=self.s18,
        )
        self.rider = RiderProfile.objects.create(
            user=rider_user, branch=self.s18,
            status=RiderProfile.DutyStatus.AVAILABLE,
        )
        category = Category.objects.create(name='Phase 8', slug='phase-8')
        self.product = Product.objects.create(
            name='Packed Handbag', slug='packed-handbag', sku='P8-BAG-1',
            category=category, price=Decimal('1800.00'),
        )
        self.stock = Stock.objects.create(
            branch=self.s18, product=self.product, quantity=10,
        )

    def make_order(self, *, order_type=Order.OrderType.ONLINE_PICKUP,
                   status=Order.Status.PROCESSING, payment=Order.PaymentMethod.MPESA_STK):
        order = Order.objects.create(
            branch=self.s18, customer=self.customer, order_type=order_type,
            customer_phone=self.customer.phone_number, customer_name='Phase Customer',
            payment_method=payment, status=status, processed_by=self.customer,
            subtotal=Decimal('3600.00'), total_payable=Decimal('3600.00'),
            pickup_code='P8A123',
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=2,
            unit_price=Decimal('1800.00'),
        )
        return order

    def test_packing_requires_every_line_before_packed(self):
        order = self.make_order()
        checklist = FulfilmentService.start_packing(
            order_id=order.pk, actor=self.staff, note='Verify colour and condition.',
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PACKING)
        self.assertEqual(checklist.lines.count(), 1)
        with self.assertRaises(ValidationError):
            FulfilmentService.complete_packing(checklist_id=checklist.pk, actor=self.staff)

        FulfilmentService.check_line(
            checklist_id=checklist.pk, line_id=checklist.lines.get().pk, actor=self.staff,
        )
        checklist = FulfilmentService.complete_packing(
            checklist_id=checklist.pk, actor=self.staff,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PACKED)
        self.assertEqual(checklist.completed_by, self.staff)
        self.assertIsNotNone(checklist.completed_at)

    @patch('notifications.tasks.send_pickup_ready_sms.delay')
    def test_s18_pickup_ready_sets_two_working_day_deadline(self, mock_sms):
        order = self.make_order(status=Order.Status.PACKED)
        before = timezone.now()
        with self.captureOnCommitCallbacks(execute=True):
            order = FulfilmentService.mark_ready_for_pickup(
                order_id=order.pk, actor=self.staff,
            )
        self.assertEqual(order.status, Order.Status.READY_FOR_PICKUP)
        self.assertGreaterEqual(order.pickup_expires_at, add_working_days(before, 2))
        mock_sms.assert_called_once_with(str(order.pk))

    def test_non_pickup_branch_cannot_mark_order_ready(self):
        order = self.make_order(status=Order.Status.PACKED)
        order.branch = self.b03
        order.save(update_fields=['branch'])
        b03_staff = User.objects.create_user(
            username='phase8b03staff', phone_number='+254733810005',
            email='phase8.b03@example.test', password='StrongPass123!',
            role=User.Role.STAFF, branch=self.b03,
        )
        with self.assertRaises(ValidationError):
            FulfilmentService.mark_ready_for_pickup(order_id=order.pk, actor=b03_staff)

    def test_manager_assignment_does_not_claim_dispatch(self):
        order = self.make_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.PACKED,
        )
        assignment, order = FulfilmentService.assign_rider(
            order_number=order.order_number,
            rider_profile_id=self.rider.pk,
            actor=self.manager,
        )
        self.assertEqual(order.status, Order.Status.RIDER_ASSIGNED)
        self.assertEqual(assignment.status, DeliveryAssignment.DeliveryStatus.ASSIGNED)
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.status, RiderProfile.DutyStatus.BUSY)

    def test_workspace_runs_packing_actions(self):
        order = self.make_order()
        self.client.force_login(self.staff)
        response = self.client.get(reverse('logistics:fulfilment-workspace'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.order_number)
        self.assertContains(response, 'Start packing')

        self.client.post(reverse('logistics:packing-start', args=[order.pk]), {
            'workspace_branch': self.s18.pk,
        })
        checklist = PackingChecklist.objects.get(order=order)
        line = checklist.lines.get()
        self.client.post(
            reverse('logistics:packing-line-check', args=[checklist.pk, line.pk]),
            {'workspace_branch': self.s18.pk},
        )
        self.client.post(
            reverse('logistics:packing-complete', args=[checklist.pk]),
            {'workspace_branch': self.s18.pk},
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PACKED)

    def test_workspace_clearly_labels_delivery_and_pickup_orders(self):
        pickup = self.make_order()
        delivery = self.make_order(order_type=Order.OrderType.ONLINE_DELIVERY)
        delivery.delivery_address = 'Nairobi CBD parcel desk'
        delivery.save(update_fields=['delivery_address'])
        self.client.force_login(self.staff)

        response = self.client.get(reverse('logistics:fulfilment-workspace'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'data-order-type="{Order.OrderType.ONLINE_PICKUP}"',
        )
        self.assertContains(
            response,
            f'data-order-type="{Order.OrderType.ONLINE_DELIVERY}"',
        )
        self.assertContains(response, 'S18 PICKUP')
        self.assertContains(response, 'DELIVERY')
        self.assertContains(response, '<strong>Collect at:</strong>', html=True)
        self.assertContains(response, '<strong>Deliver to:</strong>', html=True)
        self.assertContains(response, pickup.order_number)
        self.assertContains(response, delivery.order_number)

    def test_workspace_limits_repeated_pickup_code_attempts(self):
        self.make_order(status=Order.Status.READY_FOR_PICKUP)
        self.client.force_login(self.staff)
        url = reverse('logistics:workspace-confirm-pickup')
        for attempt in range(11):
            response = self.client.post(
                url,
                {'workspace_branch': self.s18.pk, 'pickup_code': 'BAD999'},
                follow=attempt == 10,
            )
        self.assertContains(response, 'Too many attempts')

    def test_tracking_payload_includes_pickup_deadline(self):
        order = self.make_order(status=Order.Status.READY_FOR_PICKUP)
        order.pickup_expires_at = add_working_days(timezone.now(), 2)
        order.save(update_fields=['pickup_expires_at'])
        self.client.force_login(self.customer)
        response = self.client.get(reverse('orders:status', args=[order.order_number]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['pickup_expires_at'])

    @override_settings(WHATSAPP_ORDER_PHONE='+254739150246')
    def test_whatsapp_order_cta_uses_configured_business_number(self):
        response = self.client.get(reverse('core:storefront_home'))
        self.assertContains(response, 'https://wa.me/254739150246')
        self.assertContains(response, 'Order via WhatsApp')

    def test_whatsapp_order_cta_defaults_to_approved_0116_number(self):
        response = self.client.get(reverse('core:storefront_home'))
        self.assertContains(response, 'https://wa.me/254116153335')

    @override_settings(WHATSAPP_ORDER_PHONE='')
    def test_whatsapp_order_cta_hidden_without_approved_number(self):
        response = self.client.get(reverse('core:storefront_home'))
        self.assertNotContains(response, 'Order via WhatsApp')


class WorkingDayCalculationTests(TestCase):
    def test_friday_plus_two_working_days_is_monday_when_saturday_is_open(self):
        friday = timezone.make_aware(datetime(2026, 7, 24, 14, 0))
        self.assertEqual(add_working_days(friday, 2).weekday(), 0)
        self.assertEqual(add_working_days(friday, 2).day, 27)

    def test_saturday_plus_one_working_day_skips_sunday(self):
        saturday = timezone.make_aware(datetime(2026, 7, 25, 14, 0))
        self.assertEqual(add_working_days(saturday, 1).weekday(), 0)
        self.assertEqual(add_working_days(saturday, 1).day, 27)
