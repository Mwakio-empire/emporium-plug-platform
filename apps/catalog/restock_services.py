from django.core.exceptions import ValidationError
from django.db.models import F, Sum
from django.utils import timezone

from inventory.models import Stock

from .models import Product, ProductVariant, RestockSubscription


def available_quantity(*, product=None, variant=None):
    if bool(product) == bool(variant):
        raise ValidationError('Choose exactly one product or variant.')
    filters = {'variant': variant} if variant is not None else {
        'product': product, 'variant__isnull': True,
    }
    return Stock.objects.filter(**filters).aggregate(
        total=Sum(F('quantity') - F('reserved_quantity')),
    )['total'] or 0


def create_restock_subscription(*, product, variant, phone_number, customer=None):
    if product.status != Product.Status.ACTIVE or not product.category.is_visible:
        raise ValidationError('This product is not available for restock alerts.')
    has_variants = product.variants.filter(is_active=True).exists()
    if has_variants:
        if variant is None or variant.product_id != product.pk or not variant.is_active:
            raise ValidationError('Choose the exact product option you want us to watch.')
        target = {'variant': variant}
    else:
        if variant is not None:
            raise ValidationError('That product option is not available.')
        target = {'product': product}
    if available_quantity(**target) > 0:
        raise ValidationError('This item is already available to order.')
    return RestockSubscription.objects.create_for_target(
        **target, phone_number=phone_number, customer=customer,
    )


def cancel_restock_subscription(subscription):
    if subscription.status == RestockSubscription.Status.ACTIVE:
        subscription.status = RestockSubscription.Status.CANCELLED
        subscription.cancelled_at = timezone.now()
        subscription.save(update_fields=['status', 'cancelled_at', 'updated_at'])
    return subscription
