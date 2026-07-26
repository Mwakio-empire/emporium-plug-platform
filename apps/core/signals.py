# apps/core/signals.py
#
# Bug: none of the three handlers guard against cache backend failures.
# A cache invalidation signal must NEVER be allowed to break the primary
# database write it's attached to. Right now, if Redis has any outage,
# every single Product/Category save() or delete() in the entire system
# throws an uncaught ConnectionError -- meaning staff cannot create,
# update, or delete catalog items until Redis comes back. Stale cache
# for a few minutes is a minor inconvenience; a broken save() is not.
#
# Exception handling here is deliberately broad (Exception, not a narrow
# type) -- unlike JSON parsing elsewhere in this project where I narrowed
# to JSONDecodeError specifically. The intent here is universal graceful
# degradation: whatever goes wrong in the cache layer (connection refused,
# timeout, auth failure, backend misconfiguration), the DB write must
# still succeed. Narrowing this exception type would defeat that purpose.

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from catalog.models import Product, Category
from core.services import HighPerformanceOptimizationService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def trigger_cache_clear_on_product_save(sender, instance, **kwargs):
    """Clears product cache on create/update. Cache failure never blocks the save."""
    try:
        HighPerformanceOptimizationService.invalidate_product_cache(instance.id)
    except Exception as e:
        logger.warning(
            f"Cache invalidation failed for Product {instance.id} on save "
            f"(save itself succeeded): {e}"
        )


@receiver(post_delete, sender=Product)
def trigger_cache_clear_on_product_erasure(sender, instance, **kwargs):
    """Clears product cache on delete. Cache failure never blocks the delete."""
    try:
        HighPerformanceOptimizationService.invalidate_product_cache(instance.id)
    except Exception as e:
        logger.warning(
            f"Cache invalidation failed for Product {instance.id} on delete "
            f"(delete itself succeeded): {e}"
        )


@receiver(post_save, sender=Category)
def trigger_cache_clear_on_category_change(sender, instance, **kwargs):
    """Clears the category tree cache. Cache failure never blocks the save."""
    from django.core.cache import cache
    try:
        cache.delete("catalog:categories:active_tree")
    except Exception as e:
        logger.warning(
            f"Cache invalidation failed for Category {instance.id} on save "
            f"(save itself succeeded): {e}"
        )