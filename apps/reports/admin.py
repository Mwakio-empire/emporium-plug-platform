from django.contrib import admin
from .models import (
    POSShift, ScheduledReport, ScheduledReportDelivery, ShiftReconciliation,
)


@admin.register(POSShift)
class POSShiftAdmin(admin.ModelAdmin):
    list_display = ('id', 'branch', 'cashier', 'status', 'opening_cash', 'opened_at', 'closed_at')
    list_filter = ('status', 'branch', 'opened_at')
    search_fields = ('cashier__username', 'branch__name')
    readonly_fields = (
        'branch', 'cashier', 'status', 'opening_cash', 'opened_at', 'closed_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ShiftReconciliation)
class ShiftReconciliationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'branch', 'cashier', 'expected_cash', 'actual_cash',
        'cash_variance', 'requires_manager_review', 'is_verified_by_manager', 'closed_at',
    )
    list_filter = ('requires_manager_review', 'is_verified_by_manager', 'branch', 'closed_at')
    search_fields = ('cashier__username', 'branch__name')
    readonly_fields = tuple(field.name for field in ShiftReconciliation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'frequency', 'branch', 'recipient_email', 'is_active',
        'next_run_at', 'last_sent_at',
    )
    list_filter = ('frequency', 'is_active', 'branch')
    search_fields = ('name', 'recipient_email')
    readonly_fields = ('created_by', 'last_sent_at', 'created_at')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.role == 'SUPER_ADMIN'

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(ScheduledReportDelivery)
class ScheduledReportDeliveryAdmin(admin.ModelAdmin):
    list_display = ('schedule', 'period_start', 'period_end', 'status', 'attempted_at', 'sent_at')
    list_filter = ('status', 'attempted_at')
    search_fields = ('schedule__name', 'schedule__recipient_email', 'error_summary')
    readonly_fields = tuple(field.name for field in ScheduledReportDelivery._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
