from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .forms import ProductVariantAdminForm
from .models import (
    Category,
    Product,
    ProductImage,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    QuantityPriceTier,
    RestockSubscription,
)
from .variant_services import generate_missing_combinations


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class ProductOptionInline(admin.TabularInline):
    model = ProductOption
    fields = ('name', 'display_type', 'position')
    extra = 0
    show_change_link = True


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    fields = ('sku', 'combination_label', 'price_override', 'is_active')
    readonly_fields = ('sku', 'combination_label')
    extra = 0
    show_change_link = True

    @admin.display(description='Combination')
    def combination_label(self, obj):
        return obj.option_summary if obj.pk else 'Save the product, then configure its variants.'


class QuantityPriceTierInline(admin.TabularInline):
    model = QuantityPriceTier
    fields = ('minimum_quantity', 'discount_percentage', 'is_active')
    extra = 0


@admin.action(description='Generate missing combinations from configured options')
def generate_product_variants(modeladmin, request, queryset):
    created_total = 0
    failures = []
    for product in queryset:
        try:
            created_total += len(generate_missing_combinations(product.pk))
        except ValidationError as exc:
            failures.append(f'{product.name}: {exc.messages[0]}')
    if created_total:
        modeladmin.message_user(
            request, f'Created {created_total} missing variant combination(s).', messages.SUCCESS,
        )
    for failure in failures:
        modeladmin.message_user(request, failure, messages.WARNING)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'sku', 'category', 'price', 'minimum_order_quantity', 'status',
        'customer_return_policy', 'updated_at',
    )
    list_filter = ('status', 'customer_return_policy', 'category')
    search_fields = ('name', 'sku', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (
        ProductOptionInline,
        ProductVariantInline,
        QuantityPriceTierInline,
        ProductImageInline,
    )
    actions = (generate_product_variants,)


class ProductOptionValueInline(admin.TabularInline):
    model = ProductOptionValue
    fields = ('value', 'colour_hex', 'position')
    extra = 1


@admin.register(ProductOption)
class ProductOptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'display_type', 'position')
    list_filter = ('display_type',)
    search_fields = ('name', 'product__name', 'product__sku')
    inlines = (ProductOptionValueInline,)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    form = ProductVariantAdminForm
    list_display = ('sku', 'product', 'combination_label', 'effective_price', 'is_active')
    list_filter = ('is_active', 'product__category')
    search_fields = ('sku', 'product__name', 'attribute_name', 'attribute_value')
    readonly_fields = ('combination_signature',)

    @admin.display(description='Combination')
    def combination_label(self, obj):
        return obj.option_summary


@admin.register(RestockSubscription)
class RestockSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('item_label', 'masked_phone', 'status', 'created_at', 'expires_at', 'notified_at')
    list_filter = ('status', 'created_at', 'expires_at')
    search_fields = ('product__name', 'variant__product__name', 'variant__sku')
    readonly_fields = tuple(field.name for field in RestockSubscription._meta.fields)
    ordering = ('-created_at',)

    @admin.display(description='Phone')
    def masked_phone(self, obj):
        return f'{obj.phone_number[:4]}*****{obj.phone_number[-3:]}'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'is_visible')
    list_filter = ('is_visible',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
