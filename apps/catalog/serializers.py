# apps/catalog/serializers.py

from rest_framework import serializers
from django.db.models import Sum
from .models import (
    Category, Product, ProductImage, ProductOption, ProductOptionValue,
    ProductOptionValueImage, ProductVariant,
)
from inventory.models import Stock
from .stock_presentation import public_stock_status


def _stock_for_requested_branch(queryset, request):
    raw_branch = request.query_params.get('branch') if request else None
    if raw_branch in (None, ''):
        return queryset
    try:
        return queryset.filter(branch_id=int(raw_branch))
    except (TypeError, ValueError):
        return queryset.none()


def _available_total(queryset):
    totals = queryset.aggregate(
        on_hand=Sum('quantity'),
        reserved=Sum('reserved_quantity'),
    )
    return (totals['on_hand'] or 0) - (totals['reserved'] or 0)


class CategorySerializer(serializers.ModelSerializer):
    """Flat category for breadcrumbs and dropdowns."""

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent']


class CategoryTreeSerializer(serializers.ModelSerializer):
    """
    Nested category tree for storefront navigation.
    Children embedded inside parent recursively.
    Note: related_name on your model is 'subcategories' — used here correctly.
    """
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'children']

    def get_children(self, obj):
        return CategoryTreeSerializer(
            obj.subcategories.filter(is_visible=True),
            many=True,
        ).data


class ProductOptionValueImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductOptionValueImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order']

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None


class ProductOptionValueSerializer(serializers.ModelSerializer):
    images = ProductOptionValueImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductOptionValue
        fields = ['id', 'value', 'colour_hex', 'position', 'images']


class ProductOptionSerializer(serializers.ModelSerializer):
    values = ProductOptionValueSerializer(many=True, read_only=True)

    class Meta:
        model = ProductOption
        fields = ['id', 'name', 'display_type', 'position', 'values']


class ProductVariantSerializer(serializers.ModelSerializer):
    """
    Variant detail with stock via database aggregation.
    Uses attribute_name + attribute_value — matches your actual model fields.
    """
    effective_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
    )
    in_stock = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    option_value_ids = serializers.PrimaryKeyRelatedField(
        source='option_values', many=True, read_only=True,
    )
    option_summary = serializers.CharField(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'sku', 'attribute_name', 'attribute_value',
            'option_value_ids', 'option_summary', 'image_url', 'is_active',
            'price_override', 'effective_price',
            'in_stock', 'stock_status',
        ]

    def _available_stock(self, obj):
        stocks = _stock_for_requested_branch(
            Stock.objects.filter(variant=obj), self.context.get('request'),
        )
        return _available_total(stocks)

    def get_in_stock(self, obj):
        return self._available_stock(obj) > 0

    def get_stock_status(self, obj):
        return public_stock_status(
            self._available_stock(obj), obj.product.low_stock_threshold,
        )

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order']

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None


class ProductListSerializer(serializers.ModelSerializer):
    """
    Lightweight product card for listing grids.
    Uses your model's single `image` field — no ProductImage model exists.
    """
    category_name = serializers.CharField(source='category.name', read_only=True)
    image_url = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    on_sale = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'category_name',
            'price', 'compare_at_price', 'on_sale',
            'image_url', 'in_stock', 'stock_status', 'status',
        ]

    def get_image_url(self, obj):
        """Returns Cloudinary URL for the product image, or None."""
        return obj.image.url if obj.image else None

    def get_in_stock(self, obj):
        """
        Single aggregate query — database does the sum, not Python.
        Checks both variant stock and direct product stock.
        """
        return obj.available_stock > 0

    def get_stock_status(self, obj):
        return public_stock_status(obj.available_stock, obj.low_stock_threshold)

    def get_on_sale(self, obj):
        return bool(obj.compare_at_price and obj.compare_at_price > obj.price)


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Full product detail for the product page.
    Includes all variants and stock status.
    """
    category = CategorySerializer(read_only=True)
    variants = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    on_sale = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    gallery = ProductImageSerializer(source='gallery_images', many=True, read_only=True)
    options = ProductOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'sku',
            'category', 'price', 'compare_at_price', 'on_sale',
            'image_url', 'variants', 'options',
            'in_stock', 'stock_status', 'status',
            'customer_return_policy',
            'weight', 'dimensions', 'specifications', 'meta_description', 'gallery',
        ]

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None

    def get_variants(self, obj):
        return ProductVariantSerializer(
            obj.variants.filter(is_active=True),
            many=True,
            context=self.context,
        ).data

    def get_total_stock(self, obj):
        request = self.context.get('request')
        variant_stocks = _stock_for_requested_branch(
            Stock.objects.filter(variant__product=obj), request,
        )
        direct_stocks = _stock_for_requested_branch(Stock.objects.filter(
            product=obj,
            variant__isnull=True,
        ), request)
        return _available_total(variant_stocks) + _available_total(direct_stocks)

    def get_in_stock(self, obj):
        return self.get_total_stock(obj) > 0

    def get_stock_status(self, obj):
        return public_stock_status(
            self.get_total_stock(obj), obj.low_stock_threshold,
        )

    def get_on_sale(self, obj):
        return bool(obj.compare_at_price and obj.compare_at_price > obj.price)
