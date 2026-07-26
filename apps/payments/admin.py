from django.contrib import admin
from .models import MpesaTransaction, MpesaWebhookEvent


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'order', 'status', 'expected_amount', 'amount',
        'confirmation_method', 'created_at',
    )
    list_filter = ('status', 'confirmation_method', 'created_at')
    search_fields = (
        'order__order_number', 'merchant_request_id', 'checkout_request_id',
        'mpesa_receipt_number', 'submitted_reference',
    )
    readonly_fields = (
        'order', 'merchant_request_id', 'checkout_request_id', 'status',
        'expected_amount', 'amount', 'requested_phone_number', 'account_reference',
        'submitted_reference', 'mpesa_receipt_number', 'failure_reason',
        'confirmation_method', 'confirmed_by', 'raw_callback_payload',
        'initiation_attempts', 'query_confirmed_at', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MpesaWebhookEvent)
class MpesaWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'processing_status', 'outcome', 'payment',
        'delivery_count', 'last_received_at',
    )
    list_filter = ('processing_status', 'outcome', 'last_received_at')
    search_fields = (
        'payload_sha256', 'checkout_request_id', 'merchant_request_id',
        'payment__order__order_number',
    )
    readonly_fields = (
        'payload_sha256', 'payload_size', 'delivery_count', 'payment',
        'checkout_request_id', 'merchant_request_id', 'result_code',
        'processing_status', 'outcome', 'review_reason', 'sanitized_evidence',
        'first_received_at', 'last_received_at', 'processed_at',
        'resolved_at', 'resolved_by', 'resolution_note',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
