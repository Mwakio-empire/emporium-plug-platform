from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PrivacyRequest, User


@admin.register(User)
class SecureUserAdmin(UserAdmin):
    """Staff provisioning is deliberately limited to Django superusers."""

    list_display = ('username', 'phone_number', 'email', 'role', 'branch', 'is_active')
    list_filter = ('role', 'branch', 'is_active')
    search_fields = ('username', 'phone_number', 'email')
    readonly_fields = (
        'last_login', 'date_joined', 'failed_login_attempts', 'locked_until',
        'last_failed_login_at', 'token_version', 'last_password_change_at',
    )
    fieldsets = UserAdmin.fieldsets + (
        ('Retail authorization', {'fields': ('phone_number', 'role', 'branch')}),
        ('Authentication security', {'fields': (
            'failed_login_attempts', 'locked_until', 'last_failed_login_at',
            'token_version', 'last_password_change_at',
        )}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Retail authorization', {'fields': ('phone_number', 'email', 'role', 'branch')}),
    )

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(PrivacyRequest)
class PrivacyRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'request_type', 'status', 'user_id', 'created_at', 'handled_at')
    list_filter = ('request_type', 'status')
    readonly_fields = (
        'user', 'request_type', 'details', 'status', 'created_at', 'updated_at',
        'handled_at', 'handled_by', 'response_note',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and request.method in {'GET', 'HEAD', 'OPTIONS'}

    def has_delete_permission(self, request, obj=None):
        return False
