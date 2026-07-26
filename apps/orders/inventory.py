from django.db import transaction

from inventory.services import InventoryService


class OrderInventoryService:
    """Apply idempotent inventory effects for all lines of one online order."""

    @staticmethod
    @transaction.atomic
    def consume_reservations(*, order, actor, note):
        results = []
        for item in order.items.select_related('variant', 'product').all():
            results.append(InventoryService.consume_reservation(
                branch=order.branch,
                quantity=item.quantity,
                triggered_by=actor,
                variant=item.variant,
                product=item.product,
                reference_number=order.order_number,
                note=note,
            ))
        return results

    @staticmethod
    @transaction.atomic
    def release_reservations(*, order, actor, note):
        results = []
        for item in order.items.select_related('variant', 'product').all():
            results.append(InventoryService.release_reservation(
                branch=order.branch,
                quantity=item.quantity,
                triggered_by=actor,
                variant=item.variant,
                product=item.product,
                reference_number=order.order_number,
                note=note,
            ))
        return results
