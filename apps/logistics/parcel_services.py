from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import ParcelDestination


class ParcelPricingService:
    """Single policy boundary for parcel availability, weight and pricing."""

    @staticmethod
    def active_destinations(on_date=None):
        day = on_date or timezone.localdate()
        return ParcelDestination.objects.filter(
            is_active=True,
            county__is_active=True,
            effective_from__lte=day,
        ).filter(Q(effective_until__isnull=True) | Q(effective_until__gte=day))

    @staticmethod
    def cart_weight(cart):
        total = Decimal('0.00')
        missing = []
        for item in cart.get_cart_items_extended():
            weight = Decimal(str(item['product'].weight or 0))
            if weight <= 0:
                missing.append(item['product'].name)
            total += weight * int(item['quantity'])
        if missing:
            names = ', '.join(sorted(set(missing)))
            raise ValidationError(
                f'Parcel delivery is unavailable until weight is configured for: {names}.'
            )
        if total <= 0:
            raise ValidationError('Parcel delivery requires a positive cart weight.')
        return total.quantize(Decimal('0.01'))

    @classmethod
    def quote(cls, *, destination_id, cart):
        try:
            destination = cls.active_destinations().select_related('county').get(
                pk=destination_id,
            )
        except ParcelDestination.DoesNotExist:
            raise ValidationError('Select an active parcel destination.')
        weight = cls.cart_weight(cart)
        return destination, weight, destination.fee_for_weight(weight)
