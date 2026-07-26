import logging
from django.core.cache import cache
from django.conf import settings
from catalog.models import Product

logger = logging.getLogger(__name__)


class CatalogCacheCoordinator:
    """
    High-performance caching wrapper optimizing database read pressures
    for standard digital storefront queries.
    """
    
    # Standardized Namespace Keys
    CATALOG_LIST_KEY = "catalog:products:all"
    PRODUCT_DETAIL_PREFIX = "catalog:product:id:"

    @classmethod
    def get_cached_active_catalog(cls):
        """
        Retrieves the complete active product portfolio. Falls back to the 
        PostgreSQL instance transparently on cache misses.
        """
        cached_data = cache.get(cls.CATALOG_LIST_KEY)
        
        if cached_data is not None:
            logger.info("Performance Hit: Active catalog fetched cleanly out of Redis memory layer.")
            return cached_data

        logger.warning("Performance Miss: Fetching portfolio dataset from PostgreSQL. Populating cache layer...")
        
        # Database fallback evaluation execution
        # Optimized with select_related/prefetch_related to prevent N+1 queries during serialization
        active_products = list(
            Product.objects.filter(status=Product.Status.ACTIVE)
            .select_related('category')
            .only('id', 'name', 'sku', 'price', 'category__name')
        )
        
        # Populate Redis memory matrix
        cache.set(cls.CATALOG_LIST_KEY, active_products, timeout=settings.CACHE_TTL_CATALOG)
        return active_products

    @classmethod
    def get_cached_product_detail(cls, product_id):
        """
        Fetches an individual specific item signature card out of memory cache.
        """
        target_key = f"{cls.PRODUCT_DETAIL_PREFIX}{product_id}"
        cached_product = cache.get(target_key)

        if cached_product is not None:
            return cached_product

        try:
            product = Product.objects.select_related('category').get(id=product_id)
            cache.set(target_key, product, timeout=settings.CACHE_TTL_CATALOG)
            return product
        except Product.DoesNotExist:
            return None

    @classmethod
    def invalidate_product_footprints(cls, product_id):
        """
        Eager Cache Invalidation: Safely evicts stale product data references 
        across lists and details instantly when modifications occur.
        """
        detail_key = f"{cls.PRODUCT_DETAIL_PREFIX}{product_id}"
        
        # Evict catalog list matrix and individual record data block simultaneously
        cache.delete_many([cls.CATALOG_LIST_KEY, detail_key])
        logger.info(f"Cache Eviction: Purged keys '{cls.CATALOG_LIST_KEY}' and '{detail_key}' following core update.")