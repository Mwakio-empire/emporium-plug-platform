from django.urls import path

from .views import (
    CheckoutPageView, DeliveryQuotePageView, OrderTrackingPageView,
    download_invoice_pdf_view,
)
from .assisted_views import WhatsAppAssistedPickupView
from .delivery_quote_staff_views import DeliveryQuoteDetailView, DeliveryQuoteWorkspaceView


urlpatterns = [
    path('delivery-quotes/', DeliveryQuoteWorkspaceView.as_view(), name='delivery-quote-workspace'),
    path('delivery-quotes/<str:reference>/', DeliveryQuotePageView.as_view(), name='delivery-quote-page'),
    path('delivery-quotes/<str:reference>/staff/', DeliveryQuoteDetailView.as_view(), name='delivery-quote-detail'),
    path('checkout/', CheckoutPageView.as_view(), name='checkout-page'),
    path('track/<str:order_number>/', OrderTrackingPageView.as_view(), name='track-order'),
    path('receipt/<int:order_id>/', download_invoice_pdf_view, name='order-receipt-pdf'),
    path('assisted/whatsapp/', WhatsAppAssistedPickupView.as_view(), name='whatsapp-assisted-pickup'),
]
