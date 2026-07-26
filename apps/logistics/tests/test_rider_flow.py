# apps/logistics/tests/test_rider_flow.py
#
# Django's built-in test runner via APITestCase.
# Filename matches Root_Directory.md's own anticipated structure for
# this app (logistics/tests/test_rider_flow.py).
#
# Every field/method reference here is traced to the actual
# logistics/views.py and logistics/serializers.py content you shared
# this turn -- not an assumed draft.

from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from orders.models import Order, OrderItem
from logistics.models import (
    DeliveryZone, PickupSlot, RiderProfile,
    DeliveryAssignment, DeliveryLocationLog,
)

User = get_user_model()


class LogisticsTestDataMixin:

    def setUp(self):
        self.branch = Branch.objects.create(
            name="Logistics Test Branch", location="Test", offers_customer_pickup=True,
        )
        self.other_branch = Branch.objects.create(
            name="Other Logistics Branch", location="Elsewhere",
        )

        self.manager = User.objects.create_user(
            username='logisticsmanager0001', phone_number='+254788000001',
            email='logisticsmanager0001@test.com', first_name='Branch',
            last_name='Manager', password='ManagerPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )

        self.rider_user = User.objects.create_user(
            username='logisticsrider0001', phone_number='+254799000001',
            email='logisticsrider0001@test.com', first_name='Fast',
            last_name='Rider', password='RiderPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        self.rider_profile = RiderProfile.objects.create(
            user=self.rider_user, branch=self.branch,
            status=RiderProfile.DutyStatus.AVAILABLE,
        )

        self.other_branch_rider_user = User.objects.create_user(
            username='otherbranchrider0001', phone_number='+254799000002',
            email='otherbranchrider0001@test.com', first_name='Wrong',
            last_name='Branch', password='RiderPass123!',
            role=User.Role.STAFF, branch=self.other_branch,
        )
        self.other_branch_rider_profile = RiderProfile.objects.create(
            user=self.other_branch_rider_user, branch=self.other_branch,
            status=RiderProfile.DutyStatus.AVAILABLE,
        )

        self.staff_no_rider = User.objects.create_user(
            username='staffnorider0001', phone_number='+254799000003',
            email='staffnorider0001@test.com', first_name='Counter',
            last_name='Staff', password='StaffPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )

        self.customer = User.objects.create_user(
            username='logisticscust0001', phone_number='+254799000004',
            email='logisticscust0001@test.com', first_name='Regular',
            last_name='Customer', password='CustPass123!',
            role=User.Role.CUSTOMER,
        )

        self.category = Category.objects.create(
            name="Logistics Category", slug="logistics-category",
        )
        self.product = Product.objects.create(
            name="Logistics Product", slug="logistics-product",
            category=self.category, price=Decimal("500.00"),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch, product=self.product, quantity=20)

        self.delivery_zone = DeliveryZone.objects.create(
            branch=self.branch, name="Logistics Zone",
            fee=Decimal("150.00"), estimated_minutes=30,
        )
        self.pickup_slot = PickupSlot.objects.create(
            branch=self.branch, label="10:00 AM - 12:00 PM",
        )

    def _create_packed_order(self, order_type=Order.OrderType.ONLINE_DELIVERY):
        order = Order.objects.create(
            branch=self.branch,
            customer=self.customer,
            order_type=order_type,
            customer_phone='+254700111111',
            payment_method=Order.PaymentMethod.MPESA_STK,
            status=Order.Status.PACKED,
            processed_by=self.customer,
            subtotal=Decimal('500.00'), total_payable=Decimal('650.00'),
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=1,
            unit_price=Decimal('500.00'),
        )
        return order

    def _create_ready_for_pickup_order(self, pickup_code='ABC123'):
        order = Order.objects.create(
            branch=self.branch,
            customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254700111111',
            payment_method=Order.PaymentMethod.MPESA_STK,
            status=Order.Status.READY_FOR_PICKUP,
            pickup_code=pickup_code,
            processed_by=self.customer,
            subtotal=Decimal('500.00'), total_payable=Decimal('500.00'),
        )
        return order


class DeliveryZoneAndPickupSlotTests(LogisticsTestDataMixin, APITestCase):

    def test_zones_public_no_auth_required(self):
        """WHAT: GET /api/logistics/zones/ with no authentication
        EXPECT: 200 -- public endpoint"""
        response = self.client.get(reverse('logistics:zones'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_zones_filtered_by_branch(self):
        """WHAT: GET ?branch=<other_branch> where zone belongs to a
              different branch
        EXPECT: The zone for self.branch is NOT in the results"""
        response = self.client.get(
            reverse('logistics:zones') + f"?branch={self.other_branch.id}"
        )
        zone_ids = [z['id'] for z in response.data]
        self.assertNotIn(str(self.delivery_zone.id), zone_ids)

    def test_pickup_slots_public_no_auth_required(self):
        """WHAT: GET /api/logistics/pickup-slots/
        EXPECT: 200 -- public endpoint"""
        response = self.client.get(reverse('logistics:pickup-slots'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RiderDeliveryQueueTests(LogisticsTestDataMixin, APITestCase):

    def test_staff_without_rider_profile_cannot_access_rider_queue(self):
        """
        WHAT: A STAFF user with no RiderProfile hits their delivery queue
        EXPECT: 403 because rider access is a profile-based capability.
        """
        self.client.force_authenticate(user=self.staff_no_rider)
        response = self.client.get(reverse('logistics:rider-queue'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_without_rider_profile_cannot_access_rider_queue(self):
        """
        WHAT: BRANCH_MANAGER without a RiderProfile hits the rider queue.
        EXPECT: 403; managers assign riders but do not impersonate their queue.
        """
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(reverse('logistics:rider-queue'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rider_sees_only_their_own_active_assignments(self):
        """
        WHAT: Rider has one ASSIGNED delivery and one DELIVERED (completed)
              delivery
        EXPECT: Only the ASSIGNED one appears -- DELIVERED is excluded
                from the active queue
        """
        order_active = self._create_packed_order()
        DeliveryAssignment.objects.create(
            order=order_active, rider=self.rider_profile,
            status=DeliveryAssignment.DeliveryStatus.ASSIGNED,
        )

        order_done = self._create_packed_order()
        DeliveryAssignment.objects.create(
            order=order_done, rider=self.rider_profile,
            status=DeliveryAssignment.DeliveryStatus.DELIVERED,
        )

        self.client.force_authenticate(user=self.rider_user)
        response = self.client.get(reverse('logistics:rider-queue'))

        order_numbers = [item['order_number'] for item in response.data]
        self.assertIn(order_active.order_number, order_numbers)
        self.assertNotIn(order_done.order_number, order_numbers)

    def test_rider_does_not_see_another_riders_deliveries(self):
        """
        WHAT: Another rider (different branch) has an active assignment
        EXPECT: Not visible in THIS rider's queue
        """
        other_order = self._create_packed_order()
        other_order.branch = self.other_branch
        other_order.save(update_fields=['branch'])
        DeliveryAssignment.objects.create(
            order=other_order, rider=self.other_branch_rider_profile,
            status=DeliveryAssignment.DeliveryStatus.ASSIGNED,
        )

        self.client.force_authenticate(user=self.rider_user)
        response = self.client.get(reverse('logistics:rider-queue'))

        order_numbers = [item['order_number'] for item in response.data]
        self.assertNotIn(other_order.order_number, order_numbers)


class AssignRiderViewTests(LogisticsTestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.manager)

    def test_customer_cannot_assign_riders(self):
        """WHAT: A CUSTOMER attempts to assign a rider
        EXPECT: 403 -- IsBranchManagerOrAbove excludes customers"""
        self.client.force_authenticate(user=self.customer)
        order = self._create_packed_order()
        response = self.client.post(reverse('logistics:assign-rider'), {
            'order_number': order.order_number,
            'rider_profile_id': self.rider_profile.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_assignment(self):
        """
        WHAT: Valid PACKED order, AVAILABLE rider in the same branch
        EXPECT: 200, assignment created, order -> RIDER_ASSIGNED,
                rider -> BUSY
        """
        order = self._create_packed_order()
        response = self.client.post(reverse('logistics:assign-rider'), {
            'order_number': order.order_number,
            'rider_profile_id': self.rider_profile.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.RIDER_ASSIGNED)

        self.rider_profile.refresh_from_db()
        self.assertEqual(self.rider_profile.status, RiderProfile.DutyStatus.BUSY)

        self.assertTrue(DeliveryAssignment.objects.filter(order=order).exists())

    def test_offline_rider_cannot_be_assigned(self):
        """
        WHAT: Rider's duty status is OFFLINE, not AVAILABLE
        EXPECT: 404 -- OFFLINE riders are intentionally excluded
                (not working / gone home / phone off)
        """
        self.rider_profile.status = RiderProfile.DutyStatus.OFFLINE
        self.rider_profile.save(update_fields=['status'])

        order = self._create_packed_order()
        response = self.client.post(reverse('logistics:assign-rider'), {
            'order_number': order.order_number,
            'rider_profile_id': self.rider_profile.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_busy_rider_cannot_be_assigned(self):
        """WHAT: Rider is already BUSY on another delivery
        EXPECT: 404"""
        self.rider_profile.status = RiderProfile.DutyStatus.BUSY
        self.rider_profile.save(update_fields=['status'])

        order = self._create_packed_order()
        response = self.client.post(reverse('logistics:assign-rider'), {
            'order_number': order.order_number,
            'rider_profile_id': self.rider_profile.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rider_from_different_branch_rejected(self):
        """
        WHAT: Manager tries to assign a rider from a different branch
        EXPECT: 404 -- the query itself filters rider by
                request.user.branch, so a cross-branch rider never matches
        """
        order = self._create_packed_order()
        response = self.client.post(reverse('logistics:assign-rider'), {
            'order_number': order.order_number,
            'rider_profile_id': self.other_branch_rider_profile.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_not_packed_rejected(self):
        """WHAT: Order exists but is still PROCESSING, not PACKED
        EXPECT: 404"""
        order = self._create_packed_order()
        order.status = Order.Status.PROCESSING
        order.save(update_fields=['status'])

        response = self.client.post(reverse('logistics:assign-rider'), {
            'order_number': order.order_number,
            'rider_profile_id': self.rider_profile.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_reassignment_updates_existing_assignment(self):
        """
        WHAT: Order already has a DeliveryAssignment (e.g. first rider
              failed), manager assigns a different available rider
        EXPECT: 200, the SAME assignment row updated (not a duplicate),
                new rider correctly attached
        """
        second_rider_user = User.objects.create_user(
            username='secondrider0001', phone_number='+254799000005',
            email='secondrider0001@test.com', first_name='Second',
            last_name='Rider', password='RiderPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        second_rider_profile = RiderProfile.objects.create(
            user=second_rider_user, branch=self.branch,
            status=RiderProfile.DutyStatus.AVAILABLE,
        )

        order = self._create_packed_order()
        DeliveryAssignment.objects.create(
            order=order, rider=self.rider_profile,
            status=DeliveryAssignment.DeliveryStatus.FAILED,
        )
        # Order needs to be back in PACKED for reassignment per the view's guard
        order.status = Order.Status.PACKED
        order.save(update_fields=['status'])

        response = self.client.post(reverse('logistics:assign-rider'), {
            'order_number': order.order_number,
            'rider_profile_id': second_rider_profile.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(DeliveryAssignment.objects.filter(order=order).count(), 1)

        assignment = DeliveryAssignment.objects.get(order=order)
        self.assertEqual(assignment.rider_id, second_rider_profile.id)


class RiderUpdateDeliveryStatusTests(LogisticsTestDataMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.order = self._create_packed_order()
        self.assignment = DeliveryAssignment.objects.create(
            order=self.order, rider=self.rider_profile,
            status=DeliveryAssignment.DeliveryStatus.ASSIGNED,
        )
        self.order.status = Order.Status.RIDER_ASSIGNED
        self.order.save(update_fields=['status'])
        self.client.force_authenticate(user=self.rider_user)

    def _update_url(self):
        return reverse('logistics:update-delivery', kwargs={'assignment_id': self.assignment.id})

    def test_customer_without_rider_profile_forbidden(self):
        """WHAT: A CUSTOMER (no rider_profile, no manager role) attempts update
        EXPECT: 403 at the permission layer -- IsRiderOrAbove"""
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(self._update_url(), {'status': 'PICKED_UP'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_valid_transition_assigned_to_picked_up(self):
        """
        WHAT: ASSIGNED -> PICKED_UP (valid per VALID_TRANSITIONS)
        EXPECT: 200, assignment.status updated, dispatched_at set,
                rider.status -> BUSY, order.status -> DISPATCHED
        """
        response = self.client.post(self._update_url(), {'status': 'PICKED_UP'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'PICKED_UP')
        self.assertIsNotNone(self.assignment.dispatched_at)

        self.rider_profile.refresh_from_db()
        self.assertEqual(self.rider_profile.status, RiderProfile.DutyStatus.BUSY)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DISPATCHED)

    def test_invalid_transition_rejected(self):
        """
        WHAT: ASSIGNED -> DELIVERED directly (skipping PICKED_UP/IN_TRANSIT)
        EXPECT: 400 -- not in VALID_TRANSITIONS['ASSIGNED']
        """
        response = self.client.post(self._update_url(), {'status': 'DELIVERED'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, 'ASSIGNED')  # unchanged

    def test_gps_update_creates_location_log_and_sets_timestamp(self):
        """
        WHAT: Valid transition with latitude/longitude provided
        EXPECT: assignment.current_latitude/longitude set,
                last_location_updated_at set, a DeliveryLocationLog row
                created (history preserved, not just overwritten)
        """
        response = self.client.post(self._update_url(), {
            'status': 'PICKED_UP',
            'latitude': '-1.286389',
            'longitude': '36.817223',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assignment.refresh_from_db()
        self.assertEqual(str(self.assignment.current_latitude), '-1.286389')
        self.assertIsNotNone(self.assignment.last_location_updated_at)

        self.assertEqual(
            DeliveryLocationLog.objects.filter(assignment=self.assignment).count(), 1
        )

    def test_latitude_without_longitude_rejected(self):
        """WHAT: Only latitude provided, longitude missing
        EXPECT: 400 -- must be provided together or neither"""
        response = self.client.post(self._update_url(), {
            'status': 'PICKED_UP',
            'latitude': '-1.286389',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delivered_sets_rider_available_and_completed_at(self):
        """
        WHAT: Full valid chain ASSIGNED -> PICKED_UP -> IN_TRANSIT -> DELIVERED
        EXPECT: rider.status returns to AVAILABLE, completed_at set,
                order.status -> DELIVERED
        """
        self.client.post(self._update_url(), {'status': 'PICKED_UP'}, format='json')
        self.client.post(self._update_url(), {'status': 'IN_TRANSIT'}, format='json')
        response = self.client.post(self._update_url(), {'status': 'DELIVERED'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assignment.refresh_from_db()
        self.assertIsNotNone(self.assignment.completed_at)

        self.rider_profile.refresh_from_db()
        self.assertEqual(self.rider_profile.status, RiderProfile.DutyStatus.AVAILABLE)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)

    def test_riders_assignment_not_visible_to_other_rider(self):
        """
        WHAT: A different rider tries to update an assignment that isn't theirs
        EXPECT: 404 -- the query filters by rider=request.user.rider_profile
        """
        self.client.force_authenticate(user=self.other_branch_rider_user)
        response = self.client.post(self._update_url(), {'status': 'PICKED_UP'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ConfirmPickupViewTests(LogisticsTestDataMixin, APITestCase):

    def test_customer_cannot_confirm_pickup(self):
        """WHAT: A CUSTOMER attempts to confirm a pickup
        EXPECT: 403 -- IsStaffOrAbove explicitly excludes customers"""
        self.client.force_authenticate(user=self.customer)
        order = self._create_ready_for_pickup_order()
        response = self.client.post(reverse('logistics:confirm-pickup'), {
            'pickup_code': order.pickup_code,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rider_cannot_confirm_pickup(self):
        """
        WHAT: A profile-based rider attempts a counter-staff pickup action.
        EXPECT: 403; rider capability is deliberately separated from POS/staff duties.
        """
        self.client.force_authenticate(user=self.rider_user)
        order = self._create_ready_for_pickup_order()
        response = self.client.post(reverse('logistics:confirm-pickup'), {
            'pickup_code': order.pickup_code,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_malformed_pickup_code_rejected(self):
        """WHAT: pickup_code that isn't 6 chars A-Z0-9
        EXPECT: 400 from PickupCodeSerializer's regex validation"""
        self.client.force_authenticate(user=self.staff_no_rider)
        response = self.client.post(reverse('logistics:confirm-pickup'), {
            'pickup_code': 'abc',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_branch_order_rejected(self):
        """
        WHAT: Staff at self.branch tries to confirm a pickup code that
              belongs to an order at a different branch
        EXPECT: 404 -- branch isolation enforced
        """
        other_order = self._create_ready_for_pickup_order(pickup_code='ZZZ999')
        other_order.branch = self.other_branch
        other_order.save(update_fields=['branch'])

        self.client.force_authenticate(user=self.staff_no_rider)
        response = self.client.post(reverse('logistics:confirm-pickup'), {
            'pickup_code': 'ZZZ999',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_successful_pickup_confirmation(self):
        """
        WHAT: Valid pickup code, correct branch, order READY_FOR_PICKUP
        EXPECT: 200, order.status -> COLLECTED
        """
        order = self._create_ready_for_pickup_order(pickup_code='OK1234')
        self.client.force_authenticate(user=self.staff_no_rider)

        response = self.client.post(reverse('logistics:confirm-pickup'), {
            'pickup_code': 'ok1234',  # lowercase input -- serializer uppercases it
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COLLECTED)

    def test_already_collected_order_rejected(self):
        """WHAT: Pickup code for an order already marked COLLECTED
        EXPECT: 404 -- can't confirm the same pickup twice"""
        order = self._create_ready_for_pickup_order(pickup_code='DONE12')
        order.status = Order.Status.COLLECTED
        order.save(update_fields=['status'])

        self.client.force_authenticate(user=self.staff_no_rider)
        response = self.client.post(reverse('logistics:confirm-pickup'), {
            'pickup_code': 'DONE12',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
