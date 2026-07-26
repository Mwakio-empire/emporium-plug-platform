#apps/orders/order_urls.py  
from django.urls import path
from . import checkout_views

app_name = 'orders'

urlpatterns = [
    path('<str:order_number>/status/', checkout_views.OrderStatusView.as_view(), name='status'),
]