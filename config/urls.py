# config/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- Storefront & POS (core app) ---
    # Single include with namespace. All core URLs accessible from root.
    # The duplicate 'pos/' include is removed — it caused the W005 warning.
    path('', include('core.urls', namespace='core')),

    # --- Branch management ---
    path('branches/', include('branches.urls')),

    # --- Inventory ---
    path('inventory/', include('inventory.urls')),

    # --- Orders (HTML views — POS receipt, admin order views etc.) ---
    # Kept without namespace because orders.urls has no app_name defined.
    # If you add app_name='orders' to orders/urls.py later, add namespace here.
    path('orders/', include('orders.urls')),

    # --- Notifications ---
    path('notifications/', include('notifications.urls')),

    # --- Marketing ---
    path('marketing/', include('marketing.urls')),

    # --- Catalog API (public) ---
    path('api/catalog/', include('catalog.urls', namespace='catalog')),

    # --- User auth API ---
    path('api/users/', include('users.urls', namespace='users')),

    # --- Storefront cart (session-based, no auth required) ---
    path('cart/', include('core.cart_urls', namespace='cart')),

    # --- Checkout API (auth required) ---
    path('api/checkout/', include('orders.checkout_urls', namespace='checkout')),

    # --- Order tracking API ---
    # Separate urlconf from orders.urls so there is no namespace collision.
    path('api/orders/', include('orders.order_urls', namespace='orders')),

    # --- Logistics API (rider, pickup, delivery zones) ---
    path('api/logistics/', include('logistics.urls', namespace='logistics')),

    # --- Reports API (manager only) ---
    path('api/reports/', include('reports.urls', namespace='reports')),
    path('management/reports/', include('reports.workspace_urls', namespace='report_workspace')),

    # --- Payments webhook (must be public — no auth) ---
    path('payments/', include('payments.urls', namespace='payments')),

    path('accounts/', include('users.auth_urls', namespace='accounts')),
]
