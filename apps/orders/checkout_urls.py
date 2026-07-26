#apps/orders/checkout_urls.py

from django.urls import path
from . import checkout_views

app_name = 'checkout'

urlpatterns = [
    path('preview/', checkout_views.CheckoutPreviewView.as_view(), name='preview'),
    path('init/', checkout_views.CheckoutInitView.as_view(), name='init'),
    path('pay/', checkout_views.CheckoutPaymentInitView.as_view(), name='pay'),
    path('pay/fallback/', checkout_views.CheckoutFallbackPaymentView.as_view(), name='pay-fallback'),
]
