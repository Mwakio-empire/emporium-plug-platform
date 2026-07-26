from django.urls import path

from .views import (
    ManualPaymentConfirmationView,
    WebhookEventResolveView,
    mpesa_callback_webhook,
)

app_name = 'payments'

urlpatterns = [
    path('mpesa/callback/', mpesa_callback_webhook, name='mpesa_callback'),
    path(
        'mpesa/<int:payment_id>/manual-confirm/',
        ManualPaymentConfirmationView.as_view(),
        name='mpesa_manual_confirm',
    ),
    path(
        'mpesa/webhook-events/<int:event_id>/resolve/',
        WebhookEventResolveView.as_view(),
        name='mpesa_webhook_event_resolve',
    ),
]
