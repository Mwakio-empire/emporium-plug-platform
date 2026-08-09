from django.contrib import admin
from django.db import transaction

from analytics.models import AuditLog
from analytics.services import AuditTrackingService

from .location_services import invalidate_town_list_caches
from .models import KenyaCounty, KenyaTown, ParcelDestination, ParcelDispatch


@admin.register(KenyaCounty)
class KenyaCountyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(KenyaTown)
class KenyaTownAdmin(admin.ModelAdmin):
    list_display = ('name', 'county', 'is_active', 'source', 'source_revision')
    list_filter = ('county', 'is_active', 'source_revision')
    search_fields = ('name', 'normalized_name', 'county__name', 'county__code')
    ordering = ('county__name', 'name', 'pk')
    list_select_related = ('county',)
    autocomplete_fields = ('county',)
    actions = None

    def save_model(self, request, obj, form, change):
        previous_county_id = None
        if change and obj.pk:
            previous_county_id = (
                KenyaTown.objects.filter(pk=obj.pk)
                .values_list('county_id', flat=True)
                .first()
            )
        obj.full_clean()
        super().save_model(request, obj, form, change)
        county_codes = {obj.county_id, previous_county_id} - {None}
        transaction.on_commit(
            lambda codes=county_codes: invalidate_town_list_caches(codes),
            robust=True,
        )

    def delete_model(self, request, obj):
        county_code = obj.county_id
        super().delete_model(request, obj)
        transaction.on_commit(
            lambda: invalidate_town_list_caches({county_code}),
            robust=True,
        )

    def has_delete_permission(self, request, obj=None):
        return False


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
