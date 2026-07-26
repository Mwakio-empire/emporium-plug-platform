from django.contrib import admin

from .models import (
    LowStockAlertState, Stock, StockAuditLog, StockCount, StockCountLine,
    StockIntake, StockIntakeLine,
    TransferReceipt, TransferRequest,
)


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        'catalog_item', 'branch', 'quantity', 'reserved_quantity',
        'available', 'in_transit_quantity', 'damaged_quantity',
    )
    list_filter = ('branch',)
    search_fields = ('product__name', 'variant__product__name', 'variant__attribute_value')

    @admin.display(description='Item')
    def catalog_item(self, obj):
        return obj.variant or obj.product

    @admin.display(description='Available')
    def available(self, obj):
        return obj.available_quantity


@admin.register(StockAuditLog)
class StockAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp', 'catalog_item', 'branch', 'reason', 'change_amount',
        'running_total', 'reserved_total', 'in_transit_total', 'damaged_total',
        'reference_number',
    )
    list_filter = ('branch', 'reason')
    search_fields = ('reference_number', 'product__name', 'variant__product__name')
    readonly_fields = [field.name for field in StockAuditLog._meta.fields]

    @admin.display(description='Item')
    def catalog_item(self, obj):
        return obj.variant or obj.product

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferRequest)
class TransferRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'from_branch', 'to_branch', 'quantity', 'status',
        'received_quantity', 'requested_at', 'approved_at',
        'dispatched_at', 'confirmed_at',
    )
    list_filter = ('status', 'from_branch', 'to_branch')
    readonly_fields = [field.name for field in TransferRequest._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockIntakeLineInline(admin.TabularInline):
    model = StockIntakeLine
    extra = 0
    can_delete = False
    readonly_fields = [field.name for field in StockIntakeLine._meta.fields]


@admin.register(StockIntake)
class StockIntakeAdmin(admin.ModelAdmin):
    list_display = ('id', 'branch', 'supplier_name', 'delivery_reference', 'received_by', 'received_at')
    list_filter = ('branch', 'received_at')
    search_fields = ('supplier_name', 'delivery_reference')
    readonly_fields = [field.name for field in StockIntake._meta.fields]
    inlines = [StockIntakeLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferReceipt)
class TransferReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'transfer', 'quantity', 'received_by', 'received_at')
    readonly_fields = [field.name for field in TransferReceipt._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockCountLineInline(admin.TabularInline):
    model = StockCountLine
    extra = 0
    can_delete = False
    readonly_fields = [field.name for field in StockCountLine._meta.fields]


@admin.register(StockCount)
class StockCountAdmin(admin.ModelAdmin):
    list_display = ('id', 'branch', 'status', 'started_by', 'started_at', 'completed_at')
    list_filter = ('branch', 'status')
    readonly_fields = [field.name for field in StockCount._meta.fields]
    inlines = [StockCountLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LowStockAlertState)
class LowStockAlertStateAdmin(admin.ModelAdmin):
    list_display = ('stock', 'is_active', 'first_triggered_at', 'last_notified_at', 'resolved_at')
    list_filter = ('is_active', 'stock__branch')
    readonly_fields = [field.name for field in LowStockAlertState._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
