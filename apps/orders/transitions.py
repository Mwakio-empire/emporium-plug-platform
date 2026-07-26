from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Order, OrderStatusHistory


class OrderTransitionService:
    """Single policy boundary for persisted order status changes."""

    COMMON_TRANSITIONS = {
        Order.Status.PENDING: {
            Order.Status.PAYMENT_CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        },
        Order.Status.PAYMENT_CONFIRMED: {
            Order.Status.PROCESSING,
            Order.Status.CANCELLED,
        },
        Order.Status.PROCESSING: {
            Order.Status.PACKING,
            Order.Status.CANCELLED,
        },
        Order.Status.PACKING: {
            Order.Status.PACKED,
            Order.Status.PROCESSING,
            Order.Status.CANCELLED,
        },
        Order.Status.PACKED: {
            Order.Status.RIDER_ASSIGNED,
            Order.Status.DISPATCHED,
            Order.Status.READY_FOR_PICKUP,
            Order.Status.CANCELLED,
        },
        Order.Status.RIDER_ASSIGNED: {
            Order.Status.DISPATCHED,
            Order.Status.PACKED,
            Order.Status.CANCELLED,
        },
        Order.Status.DISPATCHED: {
            Order.Status.ARRIVED_AT_DESTINATION,
            Order.Status.OUT_FOR_DELIVERY,
            Order.Status.RETURNED,
        },
        Order.Status.ARRIVED_AT_DESTINATION: {
            Order.Status.COLLECTED,
            Order.Status.RETURNED,
        },
        Order.Status.OUT_FOR_DELIVERY: {
            Order.Status.DELIVERED,
            Order.Status.RETURNED,
        },
        Order.Status.DELIVERED: {
            Order.Status.CUSTOMER_CONFIRMED,
            Order.Status.DISPUTED,
        },
        Order.Status.DISPUTED: {
            Order.Status.CUSTOMER_CONFIRMED,
            Order.Status.RETURNED,
        },
        Order.Status.READY_FOR_PICKUP: {
            Order.Status.COLLECTED,
            Order.Status.CANCELLED,
        },
        Order.Status.COMPLETED: {Order.Status.VOIDED},
    }

    TERMINAL_STATUSES = {
        Order.Status.VOIDED,
        Order.Status.DELIVERED,
        Order.Status.COLLECTED,
        Order.Status.CANCELLED,
        Order.Status.CUSTOMER_CONFIRMED,
        Order.Status.RETURNED,
    }

    @classmethod
    def allowed_targets(cls, order):
        allowed = set(cls.COMMON_TRANSITIONS.get(order.status, set()))
        if order.order_type == Order.OrderType.WALK_IN:
            if order.status == Order.Status.PENDING:
                return {Order.Status.COMPLETED, Order.Status.CANCELLED}
            if order.status == Order.Status.COMPLETED:
                return {Order.Status.VOIDED}
            return set()
        if order.order_type == Order.OrderType.ONLINE_DELIVERY:
            allowed.discard(Order.Status.READY_FOR_PICKUP)
            if order.parcel_destination_id:
                allowed.discard(Order.Status.RIDER_ASSIGNED)
                allowed.discard(Order.Status.OUT_FOR_DELIVERY)
                allowed.discard(Order.Status.DELIVERED)
                allowed.discard(Order.Status.CUSTOMER_CONFIRMED)
                allowed.discard(Order.Status.DISPUTED)
            else:
                if order.status == Order.Status.PACKED:
                    allowed.discard(Order.Status.DISPATCHED)
                allowed.discard(Order.Status.ARRIVED_AT_DESTINATION)
                allowed.discard(Order.Status.COLLECTED)
        elif order.order_type == Order.OrderType.ONLINE_PICKUP:
            allowed.discard(Order.Status.RIDER_ASSIGNED)
            allowed.discard(Order.Status.DISPATCHED)
            allowed.discard(Order.Status.OUT_FOR_DELIVERY)
            allowed.discard(Order.Status.DELIVERED)
            allowed.discard(Order.Status.CUSTOMER_CONFIRMED)
            allowed.discard(Order.Status.DISPUTED)
            allowed.discard(Order.Status.RETURNED)
        return allowed

    @classmethod
    @transaction.atomic
    def transition(cls, *, order, to_status, changed_by, note='', extra_updates=None):
        """
        Lock, validate, persist, and audit one transition atomically.

        Returns the locked and updated Order. Callers must use the returned
        instance when they need subsequent state in the same workflow.
        """
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if to_status == locked.status:
            return locked
        if to_status not in cls.allowed_targets(locked):
            raise ValidationError(
                f"Invalid order transition: {locked.status} -> {to_status} "
                f"for {locked.order_type}. Allowed: {sorted(cls.allowed_targets(locked))}."
            )
        if changed_by is None:
            raise ValidationError("An authenticated or system actor is required for a status change.")

        old_status = locked.status
        updates = dict(extra_updates or {})
        for field, value in updates.items():
            setattr(locked, field, value)
        locked.status = to_status
        locked.save(update_fields=['status', *updates.keys()])
        OrderStatusHistory.objects.create(
            order=locked,
            old_status=old_status,
            new_status=to_status,
            note=note,
            changed_by=changed_by,
        )
        order.status = locked.status
        for field in updates:
            setattr(order, field, getattr(locked, field))
        return locked
