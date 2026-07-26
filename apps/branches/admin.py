from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'is_active', 'receives_supplier_stock')
    list_filter = ('is_active', 'receives_supplier_stock')
    search_fields = ('name', 'location')
