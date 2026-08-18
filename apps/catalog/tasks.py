import logging
from urllib.parse import urljoin

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.catalog import EventType
from notifications.tasks import queue_sms_event

from .models import Product, RestockSubscription
from .restock_services import available_quantity


logger = logging.getLogger(__name__)


@shared_task(name='catalog.send_customer_restock_alerts')
def send_customer_restock_alerts(batch_size=100):
    """Close expired requests and queue one durable SMS when stock returns."""
    now = timezone.now()
    expired = RestockSubscription.objects.filter(
        status=RestockSubscription.Status.ACTIVE,
        expires_at__lte=now,
    ).update(status=RestockSubscription.Status.EXPIRED, updated_at=now)
    candidate_ids = list(RestockSubscription.objects.filter(
        status=RestockSubscription.Status.ACTIVE,
        expires_at__gt=now,
    ).values_list('pk', flat=True)[:batch_size])
    notified = 0
    for subscription_id in candidate_ids:
        with transaction.atomic():
            subscription = RestockSubscription.objects.select_for_update(
                of=('self',),
            ).select_related(
                'product__category', 'variant__product__category',
            ).get(pk=subscription_id)
            if subscription.status != RestockSubscription.Status.ACTIVE:
                continue
            product = subscription.catalog_product
            if (
                product.status != Product.Status.ACTIVE
                or not product.category.is_visible
                or (subscription.variant_id and not subscription.variant.is_active)
            ):
                continue
            target = (
                {'variant': subscription.variant}
                if subscription.variant_id else {'product': subscription.product}
            )
            if available_quantity(**target) <= 0:
                continue
            product_url = urljoin(
                settings.SITE_BASE_URL.rstrip('/') + '/',
                reverse('core:product_detail', kwargs={'slug': product.slug}).lstrip('/'),
            )
            message = (
                f'{subscription.item_label} is available again at Emporium Plug. '
                f'Order here: {product_url} Availability can change and stock is not reserved.'
            )
            queue_sms_event(
                subscription.phone_number,
                message,
                EventType.BACK_IN_STOCK,
                'restock_subscription',
                subscription.pk,
                occurrence='available',
                defer_until_commit=True,
            )
            subscription.status = RestockSubscription.Status.NOTIFIED
            subscription.notified_at = now
            subscription.save(update_fields=['status', 'notified_at', 'updated_at'])
            notified += 1
    logger.info('Customer restock sweep completed | notified=%s expired=%s', notified, expired)
    return {'notified': notified, 'expired': expired}
