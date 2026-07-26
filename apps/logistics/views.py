# apps/logistics/views.py

import logging
import secrets
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.core.cache import cache
from orders.models import Order, OrderStatusHistory
from orders.inventory import OrderInventoryService
from orders.transitions import OrderTransitionService
from .models import (
    DeliveryAssignment, DeliveryLocationLog,
    DeliveryZone, RiderProfile, PickupSlot,
)
from .serializers import (
    DeliveryZoneSerializer,
    PickupSlotSerializer,
    DeliveryQueueItemSerializer,
    AssignRiderRequestSerializer,
    UpdateDeliveryStatusSerializer,
    PickupCodeSerializer,
)
from notifications.tasks import send_delivery_status_sms, send_collection_confirmed_sms
from users.permissions import IsRider, IsBranchManagerOrAbove, IsStaffOrAbove
from users.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)


def _queue_delivery_status_notification(order_id, delivery_status):
    try:
        send_delivery_status_sms.delay(order_id, delivery_status)
    except Exception as exc:
        logger.error(
            'Delivery notification could not be queued | OrderID=%s | ExceptionType=%s',
            order_id, type(exc).__name__,
        )

def _invalidate_report_caches(order):
    """
    Clears cached shift/branch reports affected by this order's status change.
    Called whenever an order moves to a state that changes revenue/sales counts
    (COMPLETED, VOIDED, CANCELLED, DELIVERED, COLLECTED).
    Without this, managers see stale figures for up to 5 minutes (CACHE_TTL).
    Uses cache key pattern matching the keys built in ShiftReportService —
    both staff and branch caches are cleared for today's period since that's
    the only period an in-flight order can affect.
    """
    if order.processed_by_id:
        cache.delete_pattern(f"shift:{order.processed_by_id}:today:*") \
            if hasattr(cache, 'delete_pattern') else None
    if order.branch_id:
        cache.delete_pattern(f"branch:{order.branch_id}:today:*") \
            if hasattr(cache, 'delete_pattern') else None
    # django-redis supports delete_pattern; if using a backend without it,
    # fall back to deleting the exact today key with no custom range
    if not hasattr(cache, 'delete_pattern'):
        today_key_staff = f"shift:{order.processed_by_id}:today:None:None"
        today_key_branch = f"branch:{order.branch_id}:today:None:None"
        cache.delete(today_key_staff)
        cache.delete(today_key_branch)
 
# ----------------------------------------------------------------------
# PERMISSION CLASSES
# Verified against users/models.py Role choices:
#   CUSTOMER, STAFF, INVENTORY_MANAGER, BRANCH_MANAGER, SUPER_ADMIN
# No RIDER role exists — riders identified via RiderProfile existence.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# DELIVERY ZONES & PICKUP SLOTS (public)
# ----------------------------------------------------------------------

class DeliveryZoneListView(generics.ListAPIView):
    """GET /api/logistics/zones/?branch=<uuid>"""
    serializer_class = DeliveryZoneSerializer
    permission_classes = [AllowAny]
    pagination_class = None  

    def get_queryset(self):
        qs = DeliveryZone.objects.filter(
            is_active=True
        ).select_related('branch').order_by('name')
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs


class PickupSlotListView(generics.ListAPIView):
    """GET /api/logistics/pickup-slots/?branch=<uuid>"""
    serializer_class = PickupSlotSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        qs = PickupSlot.objects.filter(
            is_active=True, branch__offers_customer_pickup=True,
        ).select_related('branch').order_by('label')
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs


# ----------------------------------------------------------------------
# RIDER PORTAL
# ----------------------------------------------------------------------

class RiderDeliveryQueueView(generics.ListAPIView):
    """
    GET /api/logistics/my-deliveries/
    Active deliveries for the authenticated rider.
    Prefetches order items — zero N+1 queries.
    """
    serializer_class = DeliveryQueueItemSerializer
    permission_classes = [IsRider]
    pagination_class = None  

    def get_queryset(self):
        try:
            rider_profile = self.request.user.rider_profile
        except RiderProfile.DoesNotExist:
            return DeliveryAssignment.objects.none()

        return DeliveryAssignment.objects.filter(
            rider=rider_profile,
            status__in=[
                DeliveryAssignment.DeliveryStatus.ASSIGNED,
                DeliveryAssignment.DeliveryStatus.PICKED_UP,
                DeliveryAssignment.DeliveryStatus.OUT_FOR_DELIVERY,
            ],
        ).select_related(
            'order__branch', 'order',
        ).prefetch_related(
            'order__items__variant__product',
            'order__items__product',
        )


class RiderUpdateDeliveryStatusView(APIView):
    """
    POST /api/logistics/delivery/<assignment_id>/update/

    - State machine enforced via DeliveryAssignment.VALID_TRANSITIONS
    - GPS coordinates stored on assignment (current) + logged in DeliveryLocationLog (history)
    - last_location_updated_at stamps every GPS update
    - Rider DutyStatus auto-updated: BUSY on PICKED_UP, AVAILABLE on DELIVERED
    - All writes inside transaction.atomic()
    - SMS dispatched via transaction.on_commit — never fires on rollback
    - Structured logging on success and failure
    """
    permission_classes = [IsRider]

    def post(self, request, assignment_id):
        serializer = UpdateDeliveryStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_status = serializer.validated_data['status']
        latitude = serializer.validated_data.get('latitude')
        longitude = serializer.validated_data.get('longitude')
        notes = serializer.validated_data.get('notes', '')

        try:
            rider_profile = request.user.rider_profile
        except RiderProfile.DoesNotExist:
            logger.warning(
                "RiderUpdateDeliveryStatus: user_id=%s has no RiderProfile.",
                request.user.pk,
            )
            return Response(
                {'error': 'No rider profile found for your account.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            assignment = DeliveryAssignment.objects.select_related(
                'order'
            ).get(id=assignment_id, rider=rider_profile)
        except DeliveryAssignment.DoesNotExist:
            logger.warning(
                "RiderUpdateDeliveryStatus: assignment %s not found for rider_user_id=%s.",
                assignment_id, request.user.pk,
            )
            return Response(
                {'error': 'Assignment not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        allowed = DeliveryAssignment.VALID_TRANSITIONS.get(assignment.status, [])
        if new_status not in allowed:
            logger.warning(
                "RiderUpdateDeliveryStatus: invalid transition %s → %s for assignment %s.",
                assignment_id, assignment.status, new_status,
            )
            return Response(
                {
                    'error': (
                        f"Invalid transition: {assignment.status} → {new_status}. "
                        f"Allowed: {allowed}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_order_status = assignment.order.status
        old_assignment_status = assignment.status

        with transaction.atomic():
            update_fields = ['status', 'delivery_notes']
            assignment.status = new_status
            if notes:
                assignment.delivery_notes = notes

            # GPS: update current position + timestamp, log to history
            if latitude is not None and longitude is not None:
                assignment.current_latitude = latitude
                assignment.current_longitude = longitude
                assignment.last_location_updated_at = timezone.now()
                update_fields += [
                    'current_latitude', 'current_longitude',
                    'last_location_updated_at',
                ]
                DeliveryLocationLog.objects.create(
                    assignment=assignment,
                    latitude=latitude,
                    longitude=longitude,
                )

            if new_status == DeliveryAssignment.DeliveryStatus.PICKED_UP:
                assignment.dispatched_at = timezone.now()
                update_fields.append('dispatched_at')
            elif new_status == DeliveryAssignment.DeliveryStatus.DELIVERED:
                assignment.completed_at = timezone.now()
                update_fields.append('completed_at')

            # Use update_fields to avoid triggering full_clean() on unchanged
            # fields — safe here because we are not changing the rider/order
            # relationship that clean() guards against
            DeliveryAssignment.objects.filter(pk=assignment.pk).update(
                **{f: getattr(assignment, f) for f in update_fields}
            )

            # Mirror status on Order
            order_status_map = {
                DeliveryAssignment.DeliveryStatus.PICKED_UP: Order.Status.DISPATCHED,
                DeliveryAssignment.DeliveryStatus.OUT_FOR_DELIVERY: Order.Status.OUT_FOR_DELIVERY,
                DeliveryAssignment.DeliveryStatus.DELIVERED: Order.Status.DELIVERED,
                DeliveryAssignment.DeliveryStatus.RETURNED: Order.Status.RETURNED,
            }
            new_order_status = order_status_map.get(new_status)
            if (
                new_status == DeliveryAssignment.DeliveryStatus.FAILED
                and old_assignment_status == DeliveryAssignment.DeliveryStatus.ASSIGNED
            ):
                new_order_status = Order.Status.PACKED
            if (
                new_status == DeliveryAssignment.DeliveryStatus.PICKED_UP
                and assignment.order.payment_method == Order.PaymentMethod.COD
            ):
                OrderInventoryService.consume_reservations(
                    order=assignment.order, actor=request.user,
                    note='COD delivery dispatched from branch.',
                )
            if new_order_status and new_order_status != old_order_status:
                assignment.order = OrderTransitionService.transition(
                    order=assignment.order,
                    to_status=new_order_status,
                    note=f"Rider updated delivery to {new_status}.",
                    changed_by=request.user,
                )

            # Update rider duty status
            if new_status == DeliveryAssignment.DeliveryStatus.DELIVERED:
                rider_profile.status = RiderProfile.DutyStatus.AVAILABLE
            elif new_status == DeliveryAssignment.DeliveryStatus.PICKED_UP:
                rider_profile.status = RiderProfile.DutyStatus.BUSY
            elif new_status in {
                DeliveryAssignment.DeliveryStatus.FAILED,
                DeliveryAssignment.DeliveryStatus.RETURNED,
            }:
                rider_profile.status = RiderProfile.DutyStatus.AVAILABLE
            rider_profile.save(update_fields=['status'])
 

        logger.info(
            "Delivery status updated | Assignment=%s | %s → %s | RiderUserID=%s",
            assignment_id, old_order_status, new_status, request.user.pk,
        )

        order_id = str(assignment.order.id)
        transaction.on_commit(
            lambda: _queue_delivery_status_notification(order_id, new_status)
        )
        if new_order_status in [Order.Status.DELIVERED, Order.Status.CANCELLED]:
           transaction.on_commit(lambda: _invalidate_report_caches(assignment.order))

        return Response({
            'success': True,
            'new_status': new_status,
            'order_number': assignment.order.order_number,
        })


# ----------------------------------------------------------------------
# MANAGER — ASSIGN RIDER
# ----------------------------------------------------------------------

class AssignRiderView(APIView):
    """
    POST /api/logistics/assign-rider/

    - select_for_update() on BOTH Order and RiderProfile prevents:
        a) Two managers assigning different riders to the same order
        b) Two managers assigning the same rider to two different orders
    - Only AVAILABLE riders can be assigned (OFFLINE excluded intentionally)
    - DeliveryAssignment update_or_create handled via explicit get_or_create
      + field assignment to guarantee full_clean() runs via model save()
    - All four writes (assignment, order status, rider status, history) atomic
    """
    permission_classes = [IsBranchManagerOrAbove]

    @transaction.atomic
    def post(self, request):
        serializer = AssignRiderRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order_number = serializer.validated_data['order_number']
        rider_profile_id = serializer.validated_data['rider_profile_id']

        # Lock Order row — prevents concurrent assignment to same order
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number,
                status=Order.Status.PACKED,
                branch=request.user.branch,
            )
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found, not in PACKED status, or not in your branch.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Lock RiderProfile row — prevents same rider being assigned twice simultaneously
        # Only AVAILABLE riders accepted — OFFLINE means not working
        try:
            rider_profile = RiderProfile.objects.select_for_update().select_related(
                'branch', 'user'
            ).get(
                id=rider_profile_id,
                branch=request.user.branch,
                status=RiderProfile.DutyStatus.AVAILABLE,
            )
        except RiderProfile.DoesNotExist:
            return Response(
                {
                    'error': (
                        'Rider not found in your branch, or not currently available. '
                        'Only riders with AVAILABLE status can be assigned.'
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        old_status = order.status

        # Explicit get_or_create + save() so model's full_clean() always runs,
        # enforcing the branch guard in DeliveryAssignment.clean()
        assignment, created = DeliveryAssignment.objects.get_or_create(
            order=order,
            defaults={
                'rider': rider_profile,
                'status': DeliveryAssignment.DeliveryStatus.ASSIGNED,
                'assigned_at': timezone.now(),
            },
        )
        if not created:
            # Re-assignment — update fields and trigger full_clean via save()
            assignment.rider = rider_profile
            assignment.status = DeliveryAssignment.DeliveryStatus.ASSIGNED
            assignment.assigned_at = timezone.now()
            assignment.delivery_notes = ''
        assignment.save()  # triggers full_clean() → branch guard enforced

        order = OrderTransitionService.transition(
            order=order,
            to_status=Order.Status.RIDER_ASSIGNED,
            changed_by=request.user,
            note=f"Rider '{rider_profile.user.get_full_name()}' assigned by manager.",
        )

        rider_profile.status = RiderProfile.DutyStatus.BUSY
        rider_profile.save(update_fields=['status'])

        logger.info(
            "Rider assigned | Order=%s | RiderUserID=%s | ManagerUserID=%s",
            order.order_number,
            rider_profile.user_id,
            request.user.pk,
        )

        return Response({
            'success': True,
            'assignment_id': str(assignment.id),
            'rider': rider_profile.user.get_full_name(),
            'order_number': order.order_number,
        })


# ----------------------------------------------------------------------
# STAFF — PICKUP CONFIRMATION
# ----------------------------------------------------------------------

class ConfirmPickupView(APIView):
    """
    POST /api/logistics/confirm-pickup/

    - IsStaffOrAbove: customers and riders explicitly excluded
    - ConfirmPickupSerializer validates 6-char A-Z0-9 format before DB hit
    - Branch isolation: staff can only confirm their own branch's orders
    - All writes atomic. SMS via transaction.on_commit.
    """
    permission_classes = [IsStaffOrAbove]

    def post(self, request):
        serializer = PickupCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        pickup_code = serializer.validated_data['pickup_code']

        if not request.user.branch:
            return Response(
                {'error': 'You are not assigned to a branch.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not request.user.branch.offers_customer_pickup:
            return Response(
                {'error': 'Pickup confirmation is restricted to the approved S18 collection branch.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            check_rate_limit(
                f"pickup_verify:{request.user.pk}:{request.META.get('REMOTE_ADDR', 'unknown')}",
                limit=10, window_seconds=300,
            )
        except ValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        candidates = Order.objects.filter(
            status=Order.Status.READY_FOR_PICKUP,
            branch=request.user.branch,
        ).order_by('-created_at')[:100]
        order = next(
            (
                candidate for candidate in candidates
                if secrets.compare_digest(candidate.pickup_code.upper(), pickup_code.upper())
            ),
            None,
        )
        if order is None:
            logger.warning(
                "ConfirmPickup: invalid code attempted by user_id=%s at branch_id=%s.",
                request.user.pk,
                request.user.branch_id,
            )
            return Response(
                {
                    'error': (
                        'Invalid pickup code, order not ready for collection, '
                        'or this order belongs to a different branch.'
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            if order.payment_method == Order.PaymentMethod.COD:
                OrderInventoryService.consume_reservations(
                    order=order,
                    actor=request.user,
                    note='COD pickup collected by customer.',
                )
            order = OrderTransitionService.transition(
                order=order,
                to_status=Order.Status.COLLECTED,
                note=f"Pickup confirmed by {request.user.get_full_name()}.",
                changed_by=request.user,
            )

        logger.info(
            "Pickup confirmed | Order=%s | StaffUserID=%s",
            order.order_number, request.user.pk,
        )

        order_id = str(order.id)
        transaction.on_commit(lambda: send_collection_confirmed_sms.delay(order_id))
        transaction.on_commit(lambda: _invalidate_report_caches(order))

        return Response({
            'success': True,
            'order_number': order.order_number,
            'customer_phone': order.customer_phone,
            'message': f"Order {order.order_number} collected successfully.",
        })
