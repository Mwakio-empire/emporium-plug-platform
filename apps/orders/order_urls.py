#apps/orders/order_urls.py  
from django.urls import path
from . import checkout_views
from .delivery_quote_views import (
    DeliveryQuoteAcceptView, DeliveryQuoteDeclineView, DeliveryQuoteStatusView,
)

app_name = 'orders'

urlpatterns = [
    path('delivery-quotes/<str:reference>/', DeliveryQuoteStatusView.as_view(), name='delivery-quote-status'),
    path('delivery-quotes/<str:reference>/accept/', DeliveryQuoteAcceptView.as_view(), name='delivery-quote-accept'),
    path('delivery-quotes/<str:reference>/decline/', DeliveryQuoteDeclineView.as_view(), name='delivery-quote-decline'),
    path('<str:order_number>/status/', checkout_views.OrderStatusView.as_view(), name='status'),
    path('<str:order_number>/cancel/', checkout_views.CustomerOrderCancellationView.as_view(), name='cancel'),
]
