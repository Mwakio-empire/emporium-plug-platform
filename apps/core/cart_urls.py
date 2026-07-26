from django.urls import path
from . import cart_views

app_name = 'cart'

urlpatterns = [
    path('', cart_views.StorefrontCartDetailView.as_view(), name='detail'),
    path('add/', cart_views.StorefrontAddToCartView.as_view(), name='add'),
    path('update/', cart_views.StorefrontUpdateCartView.as_view(), name='update'),
    path('remove/', cart_views.StorefrontRemoveFromCartView.as_view(), name='remove'),
]