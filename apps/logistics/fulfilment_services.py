import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from orders.models import Order
from orders.inventory import OrderInventoryService
from orders.transitions import OrderTransitionService
from users.models import User

from .models import (
    DeliveryAssignment, PackingChecklist, PackingChecklistItem, ParcelDispatch,
    RiderProfile,
)


logger = logging.getLogger(__name__)


def add_working_days(value, days):
    """Add Monday-Saturday business days while preserving time of day."""
    result = value
    remaining = int(days)
    while remaining > 0:
        result += timedelta(days=1)
        if result.weekday() < 6:
            remaining -= 1
    return result


class FulfilmentService:
    STAFF_ROLES = {
        User.Role.STAFF,
        User.Role.INVENTORY_MANAGER,
        User.Role.BRANCH_MANAGER,
        User.Role.SUPER_ADMIN,
    }

    @classmethod
    def _assert_branch_actor(cls, actor, branch_id):
        if actor.role not in cls.STAFF_ROLES:
            raise ValidationError('Only authorized staff may manage fulfilment.')
        if actor.role != User.Role.SUPER_ADMIN and actor.branch_id != branch_id:
            raise ValidationError('You can only manage orders assigned to your branch.')

    @classmethod
    @transaction.atomic
    def assign_rider(cls, *, order_number, rider_profile_id, actor):
        if actor.role not in {User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN}:
            raise ValidationError('Only a branch manager or super admin may assign riders.')
        order = Order.objects.select_for_update().get(
            order_number=order_number, status=Order.Status.PACKED,
        )
        cls._assert_branch_actor(actor, order.branch_id)
        if order.order_type != Order.OrderType.ONLINE_DELIVERY:
            raise ValidationError('Riders can only be assigned to delivery orders.')
        rider = RiderProfile.objects.select_for_update().select_related('user').get(
            pk=rider_profile_id, branch_id=order.branch_id,
            status=RiderProfile.DutyStatus.AVAILABLE,
        )
        assignment, _ = DeliveryAssignment.objects.get_or_create(order=order)
        assignment.rider = rider
        assignment.status = DeliveryAssignment.DeliveryStatus.ASSIGNED
        assignment.assigned_at = timezone.now()
        assignment.delivery_notes = ''
        assignment.save()
        order = OrderTransitionService.transition(
            order=order, to_status=Order.Status.RIDER_ASSIGNED, changed_by=actor,
            note=f"Rider '{rider.user.get_full_name() or rider.user.username}' assigned.",
        )
        rider.status = RiderProfile.DutyStatus.BUSY
        rider.save(update_fields=['status'])
        return assignment, order

    @classmethod
    @transaction.atomic
    def start_packing(cls, *, order_id, actor, note=''):
        order = Order.objects.select_for_update().prefetch_related('items').get(pk=order_id)
        cls._assert_branch_actor(actor, order.branch_id)
        if order.order_type == Order.OrderType.WALK_IN:
            raise ValidationError('Walk-in sales do not use the online packing workflow.')
        if order.status != Order.Status.PROCESSING:
            raise ValidationError('Only processing orders can begin packing.')
        checklist, created = PackingChecklist.objects.get_or_create(
            order=order,
            defaults={'started_by': actor, 'note': str(note or '').strip()},
        )
        if not created and checklist.completed_at is not None:
            raise ValidationError('This order already has a completed packing checklist.')
        PackingChecklistItem.objects.bulk_create(
            [PackingChecklistItem(checklist=checklist, order_item=item) for item in order.items.all()],
            ignore_conflicts=True,
        )
        OrderTransitionService.transition(
            order=order, to_status=Order.Status.PACKING, changed_by=actor,
            note='Packing checklist started.',
        )
        return checklist

    @classmethod
    @transaction.atomic
    def check_line(cls, *, checklist_id, line_id, actor):
        checklist = PackingChecklist.objects.select_for_update().select_related('order').get(
            pk=checklist_id,
        )
        cls._assert_branch_actor(actor, checklist.order.branch_id)
        if checklist.completed_at is not None or checklist.order.status != Order.Status.PACKING:
            raise ValidationError('Only an active packing checklist can be updated.')
        line = PackingChecklistItem.objects.select_for_update().get(
            pk=line_id, checklist=checklist,
        )
        if line.checked_at is None:
            line.checked_at = timezone.now()
            line.checked_by = actor
            line.save(update_fields=['checked_at', 'checked_by'])
        return line

    @classmethod
    @transaction.atomic
    def complete_packing(cls, *, checklist_id, actor):
        checklist = PackingChecklist.objects.select_for_update().select_related('order').get(
            pk=checklist_id,
        )
        cls._assert_branch_actor(actor, checklist.order.branch_id)
        lines = list(checklist.lines.select_for_update())
        if not lines or any(line.checked_at is None for line in lines):
            raise ValidationError('Check every order line before completing packing.')
        if checklist.completed_at is not None:
            return checklist
        order = OrderTransitionService.transition(
            order=checklist.order, to_status=Order.Status.PACKED, changed_by=actor,
            note='All packing checklist lines verified; parcel sealed.',
        )
        checklist.order = order
        checklist.completed_by = actor
        checklist.completed_at = timezone.now()
        checklist.save(update_fields=['completed_by', 'completed_at'])
        return checklist

    @classmethod
    @transaction.atomic
    def mark_ready_for_pickup(cls, *, order_id, actor):
        order = Order.objects.select_for_update().get(pk=order_id)
        cls._assert_branch_actor(actor, order.branch_id)
        if order.order_type != Order.OrderType.ONLINE_PICKUP:
            raise ValidationError('Only pickup orders can be marked ready for collection.')
        if not order.branch.offers_customer_pickup:
            raise ValidationError('This branch is not an approved customer pickup location.')
        days = int(getattr(settings, 'PICKUP_RESERVATION_WORKING_DAYS', 2))
        expires_at = add_working_days(timezone.now(), days)
        order = OrderTransitionService.transition(
            order=order, to_status=Order.Status.READY_FOR_PICKUP, changed_by=actor,
            note=f'Order ready for pickup; held for {days} working days.',
            extra_updates={'pickup_expires_at': expires_at},
        )
        order_id_str = str(order.pk)
        transaction.on_commit(lambda: cls._queue_ready_notification(order_id_str))
        return order

    @classmethod
    @transaction.atomic
    def dispatch_parcel(
        cls, *, order_id, actor, parcel_reference, actual_transport_cost,
        vehicle_registration='', operator_contact='', dispatch_note='',
    ):
        order = Order.objects.select_for_update().select_related('parcel_destination').get(pk=order_id)
        cls._assert_branch_actor(actor, order.branch_id)
        if not order.parcel_destination_id or order.order_type != Order.OrderType.ONLINE_DELIVERY:
            raise ValidationError('This order is not a parcel-to-town order.')
        if order.status != Order.Status.PACKED:
            raise ValidationError('Only a packed parcel can be dispatched.')
        if order.payment_method != Order.PaymentMethod.MPESA_STK:
            raise ValidationError('Parcel-to-town orders must be prepaid before dispatch.')
        reference = str(parcel_reference or '').strip()
        if not reference:
            raise ValidationError('Enter the parcel office or vehicle reference.')
        dispatch = ParcelDispatch(
            order=order,
            parcel_reference=reference,
            vehicle_registration=str(vehicle_registration or '').strip().upper(),
            operator_contact=str(operator_contact or '').strip(),
            actual_transport_cost=actual_transport_cost,
            dispatch_note=str(dispatch_note or '').strip(),
            dispatched_by=actor,
        )
        dispatch.save()
        OrderInventoryService.consume_reservations(
            order=order, actor=actor, note='Prepaid parcel handed to transport operator.',
        )
        order = OrderTransitionService.transition(
            order=order, to_status=Order.Status.DISPATCHED, changed_by=actor,
            note=f'Parcel handed to {order.parcel_operator_name}; reference {reference}.',
        )
        transaction.on_commit(lambda: cls._queue_parcel_notification(str(order.pk), 'DISPATCHED'))
        return dispatch, order

    @classmethod
    @transaction.atomic
    def mark_parcel_arrived(cls, *, order_id, actor):
        order = Order.objects.select_for_update().get(pk=order_id)
        cls._assert_branch_actor(actor, order.branch_id)
        dispatch = ParcelDispatch.objects.select_for_update().get(order=order)
        if order.status != Order.Status.DISPATCHED:
            raise ValidationError('Only a dispatched parcel can be marked arrived.')
        dispatch.arrived_by = actor
        dispatch.arrived_at = timezone.now()
        dispatch.save(update_fields=['arrived_by', 'arrived_at'])
        order = OrderTransitionService.transition(
            order=order, to_status=Order.Status.ARRIVED_AT_DESTINATION,
            changed_by=actor, note='Transport operator confirmed arrival at the destination.',
        )
        transaction.on_commit(lambda: cls._queue_parcel_notification(str(order.pk), 'ARRIVED'))
        return order

    @classmethod
    @transaction.atomic
    def mark_parcel_collected(cls, *, order_id, actor, confirmation_note):
        order = Order.objects.select_for_update().get(pk=order_id)
        cls._assert_branch_actor(actor, order.branch_id)
        note = str(confirmation_note or '').strip()
        if not note:
            raise ValidationError('Record how collection was confirmed.')
        dispatch = ParcelDispatch.objects.select_for_update().get(order=order)
        if order.status != Order.Status.ARRIVED_AT_DESTINATION:
            raise ValidationError('Only an arrived parcel can be marked collected.')
        dispatch.collected_by = actor
        dispatch.collected_at = timezone.now()
        dispatch.dispatch_note = f'{dispatch.dispatch_note}\nCollection confirmation: {note}'.strip()
        dispatch.save(update_fields=['collected_by', 'collected_at', 'dispatch_note'])
        order = OrderTransitionService.transition(
            order=order, to_status=Order.Status.COLLECTED, changed_by=actor,
            note=f'Parcel collection confirmed: {note}',
        )
        transaction.on_commit(lambda: cls._queue_parcel_notification(str(order.pk), 'COLLECTED'))
        return order

    @classmethod
    @transaction.atomic
    def confirm_pickup(cls, *, pickup_code, actor):
        if actor.branch_id is None:
            raise ValidationError('You are not assigned to a pickup branch.')
        cls._assert_branch_actor(actor, actor.branch_id)
        if not actor.branch.offers_customer_pickup:
            raise ValidationError('Pickup confirmation is restricted to the approved S18 branch.')
        candidates = list(Order.objects.select_for_update().filter(
            branch=actor.branch, status=Order.Status.READY_FOR_PICKUP,
        ).order_by('-created_at')[:100])
        normalized = str(pickup_code or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{6}', normalized):
            raise ValidationError('Enter the six-character pickup code.')
        order = next(
            (
                candidate for candidate in candidates
                if secrets.compare_digest(candidate.pickup_code.upper(), normalized)
            ),
            None,
        )
        if order is None:
            raise ValidationError('Invalid pickup code or order is not ready for collection.')
        if order.payment_method == Order.PaymentMethod.COD:
            OrderInventoryService.consume_reservations(
                order=order, actor=actor, note='COD pickup collected by customer.',
            )
        order = OrderTransitionService.transition(
            order=order, to_status=Order.Status.COLLECTED, changed_by=actor,
            note=f'Pickup confirmed by {actor.get_full_name() or actor.username}.',
        )
        order_id_str = str(order.pk)
        transaction.on_commit(lambda: cls._queue_collection_notification(order_id_str))
        return order

    @staticmethod
    def _queue_ready_notification(order_id):
        try:
            from notifications.tasks import send_pickup_ready_sms
            send_pickup_ready_sms.delay(order_id)
        except Exception as exc:
            logger.error(
                'Pickup-ready notification could not be queued | OrderID=%s | ExceptionType=%s',
                order_id, type(exc).__name__,
            )

    @staticmethod
    def _queue_collection_notification(order_id):
        try:
            from notifications.tasks import send_collection_confirmed_sms
            send_collection_confirmed_sms.delay(order_id)
        except Exception as exc:
            logger.error(
                'Collection notification could not be queued | OrderID=%s | ExceptionType=%s',
                order_id, type(exc).__name__,
            )

    @staticmethod
    def _queue_parcel_notification(order_id, parcel_status):
        try:
            from notifications.tasks import send_parcel_status_sms
            send_parcel_status_sms.delay(order_id, parcel_status)
        except Exception as exc:
            logger.error(
                'Parcel notification could not be queued | OrderID=%s | ExceptionType=%s',
                order_id, type(exc).__name__,
            )
