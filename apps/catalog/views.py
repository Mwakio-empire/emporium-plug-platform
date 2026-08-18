# apps/catalog/views.py

from rest_framework import generics, filters
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.conf import settings

from .models import Category, Product
from .serializers import (
    CategoryTreeSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
)
from .filters import ProductFilter
from .storefront import active_branches, public_products


def _requested_branch_id(request):
    raw_branch = request.query_params.get('branch')
    if raw_branch in (None, ''):
        return None
    try:
        branch_id = int(raw_branch)
    except (TypeError, ValueError):
        return 0
    return branch_id if active_branches().filter(pk=branch_id).exists() else 0


class CategoryTreeView(generics.ListAPIView):
    """
    GET /api/catalog/categories/
    Nested category tree. Cached 24 hours — changes rarely.
    """
    serializer_class = CategoryTreeSerializer
    permission_classes = [AllowAny]
    pagination_class = None   
    # Top-level only — subcategories embedded by serializer
    queryset = Category.objects.filter(
        parent__isnull=True,
        is_visible=True,
    ).prefetch_related('subcategories')

    @method_decorator(cache_page(settings.CACHE_TTL_STATIC_DATA))
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class ProductListView(generics.ListAPIView):
    """
    GET /api/catalog/products/
    Paginated listing with filtering, search, ordering.

    Query params:
        ?category=electronics    Filter by category slug
        ?min_price=500           Minimum price
        ?max_price=10000         Maximum price
        ?on_sale=true            Discounted products only
        ?in_stock=true           In-stock products only
        ?search=phone            Search name, description, sku
        ?ordering=price          Sort (prefix - for descending)
    """
    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]
    filterset_class = ProductFilter
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'sku', 'category__name']
    ordering_fields = ['price', 'created_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        # Product.Status.ACTIVE = 'ACTIVE' — using the constant, not a bare string
        return public_products(branch_id=_requested_branch_id(self.request))


class ProductDetailView(generics.RetrieveAPIView):
    """
    GET /api/catalog/products/{slug}/
    Full product detail including all variants.
    """
    serializer_class = ProductDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return public_products(
            branch_id=_requested_branch_id(self.request),
        ).prefetch_related(
            'variants__option_values',
            'options__values__images',
            'gallery_images',
        )
