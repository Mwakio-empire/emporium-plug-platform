from django.contrib import admin

from .models import (
    DeliveryQuoteClosure, DeliveryQuoteRequest, DeliveryQuoteStatusHistory,
    Order, OrderItem, OrderStatusHistory,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'variant', 'quantity', 'unit_price', 'total_price')


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ('old_status', 'new_status', 'note', 'changed_by', 'created_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Read-only evidence view; operational changes belong in validated workspaces."""

    list_display = (
        'order_number', 'status', 'sales_channel', 'order_type', 'branch',
        'payment_method', 'total_payable', 'processed_by', 'created_at',
    )
    list_filter = ('status', 'sales_channel', 'order_type', 'payment_method', 'branch')
    search_fields = ('order_number', 'customer_phone', 'customer_email', 'payment_reference')
    date_hierarchy = 'created_at'
    readonly_fields = tuple(field.name for field in Order._meta.fields)
    inlines = (OrderItemInline, OrderStatusHistoryInline)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {'GET', 'HEAD', 'OPTIONS'}

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeliveryQuoteRequest)
class DeliveryQuoteRequestAdmin(admin.ModelAdmin):
    list_display = ('reference', 'status', 'town', 'customer_phone', 'delivery_fee', 'branch', 'created_at')
    list_filter = ('status', 'branch', 'county')
    search_fields = ('reference', 'customer_name', 'customer_phone', 'town')
    readonly_fields = tuple(field.name for field in DeliveryQuoteRequest._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {'GET', 'HEAD', 'OPTIONS'}

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeliveryQuoteClosure)
class DeliveryQuoteClosureAdmin(admin.ModelAdmin):
    list_display = ('date', 'label', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('label',)


@admin.register(DeliveryQuoteStatusHistory)
class DeliveryQuoteStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('quote', 'old_status', 'new_status', 'changed_by', 'created_at')
    readonly_fields = tuple(field.name for field in DeliveryQuoteStatusHistory._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {'GET', 'HEAD', 'OPTIONS'}

    def has_delete_permission(self, request, obj=None):
        return False
