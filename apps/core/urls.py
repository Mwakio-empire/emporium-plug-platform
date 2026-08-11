# apps/core/urls.py

from django.urls import path
from core.views import (
    ProductDetailPageView,
    SentryTelemetryTriggerVerificationView,
    StorefrontHomeLandingView,
    PointOfSaleWorkspaceTerminalView,
    AsynchronousCatalogFilterEngineView,
    ReactiveCartActionGatewayView,
    NavbarCartCounterPartialView,
    AsynchronousPOSProductLookupView,
    ReactivePOSCartActionView,
    POSOrderCheckoutSubmissionView,
    POSCustomerDisplayView,
    POSCustomerDisplayPartialView,
    POSVoidSaleView,
    ShiftCloseSubmissionView,
    ShiftOpenSubmissionView,
    ShiftVerifySubmissionView,
    AnalyticsDashboardView,
    AnalyticsDashboardMetricsPartialView,
    RobotsPolicyView,
    StorefrontSitemapView,
    AboutPageView,
    FAQPageView,
    DeliveryPickupPageView,
    ReturnsPolicyPageView,
    TermsPageView,
    CategoryStorefrontView,
    WishlistPageView,
    WishlistToggleView,
    RestockSubscribeView,
    RestockCancelView,
)
from core.health import LivenessView, OperationalHealthView, ReadinessView

# app_name is required when namespace= is used in config/urls.py include()
app_name = 'core'

urlpatterns = [
    path('health/live/', LivenessView.as_view(), name='health_live'),
    path('health/ready/', ReadinessView.as_view(), name='health_ready'),
    path('health/operations/', OperationalHealthView.as_view(), name='health_operations'),
    # Storefront
path('', StorefrontHomeLandingView.as_view(), name='storefront_home'),
    path('product/<slug:slug>/', ProductDetailPageView.as_view(), name='product_detail'),
    path('category/<slug:slug>/', CategoryStorefrontView.as_view(), name='category_storefront'),
    path('catalog-filter/', AsynchronousCatalogFilterEngineView.as_view(), name='catalog_filter_engine'),
    path('sitemap.xml', StorefrontSitemapView.as_view(), name='sitemap'),
    path('robots.txt', RobotsPolicyView.as_view(), name='robots'),
    path('about/', AboutPageView.as_view(), name='about'),
    path('help/faq/', FAQPageView.as_view(), name='faq'),
    path('help/delivery-pickup/', DeliveryPickupPageView.as_view(), name='delivery_pickup'),
    path('help/returns/', ReturnsPolicyPageView.as_view(), name='returns_policy'),
    path('terms/', TermsPageView.as_view(), name='terms'),
    path('wishlist/', WishlistPageView.as_view(), name='wishlist'),
    path('wishlist/<int:product_id>/toggle/', WishlistToggleView.as_view(), name='wishlist_toggle'),
    path('restock-alerts/subscribe/', RestockSubscribeView.as_view(), name='restock_subscribe'),
    path('restock-alerts/<uuid:token>/cancel/', RestockCancelView.as_view(), name='restock_cancel'),
    # Session cart
    path('cart-gateway/', ReactiveCartActionGatewayView.as_view(), name='cart_action_gateway'),
    path('navbar-cart-counter/', NavbarCartCounterPartialView.as_view(), name='navbar_cart_counter'),

    # POS
    path('pos-desk/', PointOfSaleWorkspaceTerminalView.as_view(), name='pos_workspace'),
    path('pos-desk/lookup/', AsynchronousPOSProductLookupView.as_view(), name='pos_product_lookup'),
    path('pos-desk/cart/', ReactivePOSCartActionView.as_view(), name='pos_cart_action'),
    path('pos-desk/checkout/', POSOrderCheckoutSubmissionView.as_view(), name='pos_order_checkout'),
    path('pos-desk/customer-display/', POSCustomerDisplayView.as_view(), name='pos_customer_display'),
    path('pos-desk/customer-display/current/', POSCustomerDisplayPartialView.as_view(), name='pos_customer_display_current'),

    # Management
    path('management/dashboard/', AnalyticsDashboardView.as_view(), name='analytics_dashboard'),
    path('management/dashboard/metrics/', AnalyticsDashboardMetricsPartialView.as_view(), name='analytics_dashboard_metrics'),

    # Diagnostics
    path('diagnostics/sentry-trigger/', SentryTelemetryTriggerVerificationView.as_view(), name='sentry_trigger'),
    path('pos-desk/void/<str:order_number>/', POSVoidSaleView.as_view(), name='pos_void_sale'),
    path('pos-desk/shift/close/', ShiftCloseSubmissionView.as_view(), name='pos_shift_close'),
    path('pos-desk/shift/open/', ShiftOpenSubmissionView.as_view(), name='pos_shift_open'),
    path('pos-desk/shift/<int:reconciliation_id>/verify/', ShiftVerifySubmissionView.as_view(), name='pos_shift_verify'),

]
