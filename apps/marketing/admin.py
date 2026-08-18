from django.contrib import admin

from analytics.models import AuditLog
from analytics.services import AuditTrackingService

from .models import Coupon, CouponRedemption, FlashSale, ProductReview, ReturnRequest


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount_type', 'value', 'allow_discounted_items',
        'times_used', 'usage_limit', 'is_active',
    )
    list_filter = ('discount_type', 'allow_discounted_items', 'is_active', 'branches')
    search_fields = ('code',)
    filter_horizontal = ('branches',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AuditTrackingService.log_action(
            request.user, AuditLog.ActionTypes.PROMOTION_CHANGE,
            f'coupon_id={obj.pk}; action={"UPDATED" if change else "CREATED"}',
        )

    def delete_model(self, request, obj):
        coupon_id = obj.pk
        super().delete_model(request, obj)
        AuditTrackingService.log_action(
            request.user, AuditLog.ActionTypes.PROMOTION_CHANGE,
            f'coupon_id={coupon_id}; action=DELETED',
        )


@admin.register(FlashSale)
class FlashSaleAdmin(admin.ModelAdmin):
    list_display = ('variant', 'sale_price', 'start_time', 'end_time', 'is_active')
    list_filter = ('is_active',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AuditTrackingService.log_action(
            request.user, AuditLog.ActionTypes.PROMOTION_CHANGE,
            f'flash_sale_id={obj.pk}; variant_id={obj.variant_id}; action={"UPDATED" if change else "CREATED"}',
        )

    def delete_model(self, request, obj):
        sale_id = obj.pk
        super().delete_model(request, obj)
        AuditTrackingService.log_action(
            request.user, AuditLog.ActionTypes.PROMOTION_CHANGE,
            f'flash_sale_id={sale_id}; action=DELETED',
        )


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'order', 'customer', 'discount_amount', 'created_at')
    readonly_fields = ('coupon', 'order', 'customer', 'customer_key', 'discount_amount', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'customer', 'rating', 'is_approved', 'moderated_by', 'created_at')
    readonly_fields = (
        'product', 'customer', 'rating', 'comment', 'is_verified_purchase',
        'is_approved', 'moderated_by', 'moderated_at', 'moderation_reason', 'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'quantity', 'status', 'stock_disposition', 'refund_status', 'created_at')
    readonly_fields = [field.name for field in ReturnRequest._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
