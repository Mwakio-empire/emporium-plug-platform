from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from catalog.models import Product
from catalog.cache_services import CatalogCacheCoordinator


@receiver(post_save, sender=Product)
def clear_product_cache_on_modification(sender, instance, created, **kwargs):
    """
    Intercepts creation and update actions to clear out stale memory data.
    """
    CatalogCacheCoordinator.invalidate_product_footprints(instance.id)


@receiver(post_delete, sender=Product)
def clear_product_cache_on_erasure(sender, instance, **kwargs):
    """
    Ensures absolute data consistency if a product record is structurally deleted.
    """
    CatalogCacheCoordinator.invalidate_product_footprints(instance.id)