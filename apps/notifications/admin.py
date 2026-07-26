from django.contrib import admin

from .models import Notification, NotificationDeliveryAttempt


class NotificationDeliveryAttemptInline(admin.TabularInline):
    model = NotificationDeliveryAttempt
    extra = 0
    can_delete = False
    readonly_fields = tuple(field.name for field in NotificationDeliveryAttempt._meta.fields)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'event_type', 'branch', 'masked_recipient', 'channel',
        'criticality', 'status', 'attempt_count', 'created_at',
    )
    list_filter = ('status', 'criticality', 'channel', 'event_type', 'branch')
    search_fields = ('reference_id', 'provider_message_id', 'dedupe_key')
    readonly_fields = tuple(field.name for field in Notification._meta.fields)
    inlines = (NotificationDeliveryAttemptInline,)

    @admin.display(description='Recipient')
    def masked_recipient(self, obj):
        return f'***{obj.recipient[-4:]}' if obj.recipient else ''

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationDeliveryAttempt)
class NotificationDeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ('notification', 'attempt_number', 'channel', 'provider', 'status', 'attempted_at')
    list_filter = ('status', 'channel', 'provider', 'attempted_at')
    readonly_fields = tuple(field.name for field in NotificationDeliveryAttempt._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
