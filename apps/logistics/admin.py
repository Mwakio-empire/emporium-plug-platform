from django.contrib import admin

from analytics.models import AuditLog
from analytics.services import AuditTrackingService

from .models import KenyaCounty, ParcelDestination, ParcelDispatch


@admin.register(KenyaCounty)
class KenyaCountyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(ParcelDestination)
class ParcelDestinationAdmin(admin.ModelAdmin):
    list_display = (
        'town', 'county', 'collection_point', 'operator_name', 'fee',
        'effective_from', 'effective_until', 'is_active',
    )
    list_filter = ('county', 'is_active', 'operator_name')
    search_fields = ('town', 'collection_point', 'operator_name', 'nairobi_dispatch_point')
    autocomplete_fields = ('county',)

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)
        AuditTrackingService.log_action(
            request.user,
            AuditLog.ActionTypes.PARCEL_ROUTE_CHANGE,
            f'parcel_destination_id={obj.pk}; action={"UPDATED" if change else "CREATED"}; active={obj.is_active}',
        )

    def delete_model(self, request, obj):
        destination_id = obj.pk
        super().delete_model(request, obj)
        AuditTrackingService.log_action(
            request.user, AuditLog.ActionTypes.PARCEL_ROUTE_CHANGE,
            f'parcel_destination_id={destination_id}; action=DELETED',
        )


@admin.register(ParcelDispatch)
class ParcelDispatchAdmin(admin.ModelAdmin):
    list_display = ('order', 'parcel_reference', 'actual_transport_cost', 'dispatched_at')
    search_fields = ('order__order_number', 'parcel_reference', 'vehicle_registration')
    readonly_fields = [field.name for field in ParcelDispatch._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
