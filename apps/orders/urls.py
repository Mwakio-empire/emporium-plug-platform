from django.urls import path

from .views import CheckoutPageView, OrderTrackingPageView, download_invoice_pdf_view


urlpatterns = [
    path('checkout/', CheckoutPageView.as_view(), name='checkout-page'),
    path('track/<str:order_number>/', OrderTrackingPageView.as_view(), name='track-order'),
    path('receipt/<int:order_id>/', download_invoice_pdf_view, name='order-receipt-pdf'),
]
