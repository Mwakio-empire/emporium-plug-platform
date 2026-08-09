# apps/core/views.py

from decimal import Decimal
import logging
from urllib.parse import urlsplit
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from django.http import Http404, HttpResponse, JsonResponse, HttpResponseForbidden
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from django.utils import timezone
# now:
from django.db import models  
from django.db.models import Q, Sum, Avg, F, Count
from django.utils.http import url_has_allowed_host_and_scheme
from branches.models import Branch
from users.models import User
from users.permissions import is_pos_operator
# Internal Application App Imports (Cleaned from apps. prefixes)
from orders.cart_services import UnifiedPOSCartService, UnifiedSessionCartService
from core.services import HighPerformanceOptimizationService
from catalog.models import Product, Category, ProductVariant, WishlistItem, RestockSubscription
from catalog.restock_services import create_restock_subscription, cancel_restock_subscription
from catalog.wishlist_services import toggle_wishlist_product, wishlist_product_ids
from catalog.storefront import (
    apply_storefront_filters,
    public_products,
    visible_categories,
)
from marketing.models import FlashSale, ProductReview
from marketing.services import FeedbackService
from orders.services import POSSalesService
from orders.models import Order
from inventory.models import Stock
from logistics.location_services import TownSelectionService
from core.location_preferences import (
    SHOPPER_LOCATION_SESSION_KEY,
    human_location_label,
)

  
User = get_user_model()
logger = logging.getLogger(__name__)


class ShopperLocationPreferenceView(View):
    """Validate and remember a shopper's browsing destination in their session."""

    def post(self, request):
        use_custom_town = request.POST.get('use_custom_town') == 'true'
        try:
            resolved = TownSelectionService.resolve(
                county_code=request.POST.get('county_code', ''),
                town_id=request.POST.get('town_id') or None,
                use_custom_town=use_custom_town,
                custom_town=request.POST.get('custom_town', ''),
            )
        except ValidationError as exc:
            return JsonResponse({'error': exc.messages[0]}, status=400)

        town_id = None if use_custom_town else int(request.POST['town_id'])
        saved = {
            'county_code': str(request.POST['county_code']).strip(),
            'county_name': human_location_label(resolved.county_name),
            'town_id': town_id,
            'town_name': human_location_label(resolved.town_name),
            'use_custom_town': use_custom_town,
        }
        request.session[SHOPPER_LOCATION_SESSION_KEY] = saved
        request.session.modified = True
        return JsonResponse({
            'message': 'Shopping location saved.',
            'location': saved,
            'location_label': f"{saved['town_name']}, {saved['county_name']}",
        })


class AboutPageView(TemplateView):
    template_name = 'core/info/about.html'


class FAQPageView(TemplateView):
    template_name = 'core/info/faq.html'


class DeliveryPickupPageView(TemplateView):
    template_name = 'core/info/delivery_pickup.html'


class ReturnsPolicyPageView(TemplateView):
    template_name = 'core/info/returns.html'


class TermsPageView(TemplateView):
    template_name = 'core/info/terms.html'


def _category_navigation_tree(categories):
    nodes = {category.pk: {'category': category, 'children': []} for category in categories}
    roots = []
    for node in nodes.values():
        parent_node = nodes.get(node['category'].parent_id)
        if parent_node:
            parent_node['children'].append(node)
        else:
            roots.append(node)
    return roots


def _storefront_catalog_context(request, filter_values=None):
    filter_values = filter_values if filter_values is not None else request.GET
    products = apply_storefront_filters(
        public_products(),
        filter_values,
    ).annotate(
        approved_review_count=Count(
            'reviews',
            filter=Q(reviews__is_approved=True, reviews__is_current=True),
            distinct=True,
        ),
        approved_average_rating=Avg(
            'reviews__rating',
            filter=Q(reviews__is_approved=True, reviews__is_current=True),
        ),
    )
    now = timezone.now()
    flash_product_ids = set(FlashSale.objects.filter(
        start_time__lte=now,
        end_time__gte=now,
        is_active=True,
    ).values_list('variant__product_id', flat=True))
    page_obj = Paginator(products, 24).get_page(filter_values.get('page'))
    query_string = filter_values.urlencode() if hasattr(filter_values, 'urlencode') else ''
    wishlist_return_url = reverse('core:storefront_home')
    if query_string:
        wishlist_return_url = f'{wishlist_return_url}?{query_string}'
    wishlist_return_url = f'{wishlist_return_url}#product-grid-target'
    return {
        'products': page_obj.object_list,
        'page_obj': page_obj,
        'flash_sales': flash_product_ids,
        'selected_branch': None,
        'filter_values': filter_values,
        'wishlist_product_ids': wishlist_product_ids(request),
        'wishlist_return_url': wishlist_return_url,
    }


class WishlistToggleView(View):
    def post(self, request, product_id):
        product = get_object_or_404(
            Product,
            pk=product_id,
            status=Product.Status.ACTIVE,
            category__is_visible=True,
        )
        saved = toggle_wishlist_product(request, product)
        messages.success(request, 'Saved to your wishlist.' if saved else 'Removed from your wishlist.')
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('core:storefront_home')
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = reverse('core:storefront_home')
        elif urlsplit(next_url).path == reverse('core:catalog_filter_engine'):
            # The catalog filter endpoint renders an HTML fragment for HTMX. It
            # must never become the browser's top-level page after a form POST.
            query = urlsplit(next_url).query
            next_url = reverse('core:storefront_home')
            if query:
                next_url = f'{next_url}?{query}'
            next_url = f'{next_url}#product-grid-target'
        return redirect(next_url)


class WishlistPageView(TemplateView):
    template_name = 'core/wishlist.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product_ids = wishlist_product_ids(self.request)
        context['products'] = public_products().filter(pk__in=product_ids).order_by('-updated_at')
        context['wishlist_product_ids'] = product_ids
        context['is_guest_wishlist'] = not self.request.user.is_authenticated
        return context


class RestockSubscribeView(View):
    def post(self, request):
        from notifications.services import keyed_digest, normalize_phone
        from users.rate_limit import check_rate_limit

        next_url = request.POST.get('next') or reverse('core:storefront_home')
        if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = reverse('core:storefront_home')
        try:
            product = get_object_or_404(
                Product.objects.select_related('category'),
                pk=request.POST.get('product_id'),
                status=Product.Status.ACTIVE,
                category__is_visible=True,
            )
            variant = None
            if request.POST.get('variant_id'):
                variant = get_object_or_404(
                    ProductVariant,
                    pk=request.POST['variant_id'],
                    product=product,
                    is_active=True,
                )
            phone = normalize_phone(request.POST.get('phone_number'))
            ip = request.META.get('REMOTE_ADDR', 'unknown')
            check_rate_limit(f'restock:ip:{ip}', limit=20, window_seconds=3600)
            check_rate_limit(
                f'restock:phone:{keyed_digest(phone)}', limit=5, window_seconds=86400,
            )
            customer = request.user if request.user.is_authenticated else None
            subscription = create_restock_subscription(
                product=product,
                variant=variant,
                phone_number=phone,
                customer=customer,
            )
        except (ValidationError, ValueError) as exc:
            message = exc.messages[0] if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, message)
        else:
            request.session['restock_manage_token'] = str(subscription.unsubscribe_token)
            messages.success(
                request,
                'Alert saved. We will send one SMS when this exact item is available. '
                'Stock is not reserved.',
            )
        return redirect(next_url)


class RestockCancelView(TemplateView):
    template_name = 'core/restock_cancel.html'

    def dispatch(self, request, *args, **kwargs):
        self.subscription = get_object_or_404(
            RestockSubscription.objects.select_related('product', 'variant__product'),
            unsubscribe_token=kwargs['token'],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['subscription'] = self.subscription
        return context

    def post(self, request, *args, **kwargs):
        cancel_restock_subscription(self.subscription)
        if request.session.get('restock_manage_token') == str(self.subscription.unsubscribe_token):
            request.session.pop('restock_manage_token', None)
        messages.success(request, 'Restock alert cancelled.')
        return redirect(
            'core:product_detail', slug=self.subscription.catalog_product.slug,
        )

class AsynchronousCatalogFilterEngineView(View):
    """
    Handles real-time, non-reloading catalog filter mutations,
    scanning categories and search criteria to return partial HTML segments.
    """
    def get(self, request, *args, **kwargs):
        return render(
            request,
            'core/partials/product_grid.html',
            _storefront_catalog_context(request),
        )


class ReactiveCartActionGatewayView(View):
    """
    Handles background asynchronous cart changes (additions, count mutations, or removals)
    and swaps updated markup chunks directly into active view frames.
    """
    def post(self, request, *args, **kwargs):
        cart_service = UnifiedSessionCartService(request)
        variant_id = request.POST.get('variant_id')
        product_id = request.POST.get('product_id')
        action = request.POST.get('action')  # Expected keys: 'add', 'remove', 'decrement'
        if not action or (not variant_id and not product_id):
            return HttpResponse(status=400)
        cart_key = f"v:{variant_id}" if variant_id else f"p:{product_id}"
        result = {'success': True}
        if action == 'add':
            try:
                quantity = int(request.POST.get('quantity', 1))
            except (TypeError, ValueError):
                quantity = 0
            if quantity < 1:
                result = {'success': False, 'error': 'Enter a valid quantity of at least one.'}
            elif variant_id:
                result = cart_service.add_variant(variant_id=variant_id, quantity=quantity)
            else:
                result = cart_service.add_product(product_id=product_id, quantity=quantity)
        elif action == 'decrement':
            current_items = cart_service.get_cart_items_extended()
            current_item = next((i for i in current_items if i['key'] == cart_key), None)
            if current_item:
                result = cart_service.update_quantity(cart_key, current_item['quantity'] - 1)
        elif action == 'remove':
            cart_service.remove_item(cart_key)
        else:
            return HttpResponse(status=400)

        # Return updated visual indicators using standard HTMX response triggers
        context = {
            'cart_items': cart_service.get_cart_items_extended(),
            'cart_total': cart_service.get_total_financial_cost(),
            'cart_count': cart_service.get_total_item_count(),
            'cart_error': result.get('error') if isinstance(result, dict) else None,
            'cart_branch': Branch.objects.filter(pk=cart_service.cart_branch_id).first(),
        }
        
        response = render(request, 'core/partials/cart_drawer_content.html', context)
        # Inject custom event trigger headers so the global navigation counter updates in tandem
        response['HX-Trigger'] = 'update-navbar-cart-count'
        if request.headers.get('HX-Request') != 'true':
            if context['cart_error']:
                messages.error(request, context['cart_error'])
            else:
                messages.success(request, 'Your cart has been updated.')
            return redirect(request.META.get('HTTP_REFERER') or reverse('core:storefront_home'))
        return response

    def get(self, request, *args, **kwargs):
        """
        Renders the active cart slide-out drawer panel state framework.
        """
        cart_service = UnifiedSessionCartService(request)
        context = {
            'cart_items': cart_service.get_cart_items_extended(),
            'cart_total': cart_service.get_total_financial_cost(),
            'cart_branch': Branch.objects.filter(pk=cart_service.cart_branch_id).first(),
        }
        return render(request, 'core/partials/cart_drawer_content.html', context)


class NavbarCartCounterPartialView(View):
    """
    Returns a partial view updating the small numeric indicator on the primary navigation menu bar.
    """
    def get(self, request, *args, **kwargs):
        cart_service = UnifiedSessionCartService(request)
        return HttpResponse(f'<span class="bg-brand-600 text-white text-xs font-bold px-2 py-0.5 rounded-full" id="nav-cart-counter">{cart_service.get_total_item_count()}</span>')
    
class SentryTelemetryTriggerVerificationView(UserPassesTestMixin, View):
    """
    Secure diagnostic viewpoint forcing a programmatic execution exception
    to evaluate live Sentry exception logging capture flows.
    """
    def test_func(self):
        # Only permit global platform system managers to run telemetry traces
        return self.request.user.is_authenticated and self.request.user.is_superuser

    def get(self, request, *args, **kwargs):
        logger.info("Executing deliberate core division-by-zero telemetry error calculation...")
        # Forcing standard technical division by zero runtime failure trace
        trigger_failure = 100 / 0
        return JsonResponse({"status": "Calculated value path passed unhindered.", "result": trigger_failure})
    

class StorefrontHomeLandingView(TemplateView):
    """
    Exposes the public Jumia-style online product catalog portal,
    leveraging Phase 13 Redis hot cache lookups for maximum speed.
    """
    template_name = "core/storefront_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pull high-speed, non-N+1 pre-cached active classifications
        categories = list(visible_categories())
        context['categories'] = categories
        context.update(_storefront_catalog_context(self.request))
        context['canonical_url'] = self.request.build_absolute_uri(reverse('core:storefront_home'))
        context['page_title'] = 'Shop Online | Emporium Plug'
        context['page_meta_description'] = 'Shop quality everyday products from Emporium Plug for S18 pickup, or request a verified parcel quote to your Kenyan town.'
        context['page_heading'] = 'Quality finds. Fair value. Shop with confidence.'
        context['page_intro'] = 'Browse one simple store—we handle stock behind the scenes. Choose S18 pickup or request a verified parcel quote to your Kenyan town before paying.'
        context['prevent_indexing'] = bool(self.request.GET)
        cart = UnifiedSessionCartService(self.request)
        context.update({
            'cart_items': cart.get_cart_items_extended(),
            'cart_total': cart.get_total_financial_cost(),
            'cart_branch': Branch.objects.filter(pk=cart.cart_branch_id).first(),
        })
        return context


class CategoryStorefrontView(StorefrontHomeLandingView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = get_object_or_404(Category, slug=kwargs['slug'], is_visible=True)
        parent = category.parent
        while parent is not None:
            if not parent.is_visible:
                raise Http404
            parent = parent.parent
        filters = self.request.GET.copy()
        filters['category'] = str(category.pk)
        context.update(_storefront_catalog_context(self.request, filters))
        context.update({
            'active_category': category,
            'canonical_url': self.request.build_absolute_uri(
                reverse('core:category_storefront', kwargs={'slug': category.slug})
            ),
            'page_title': f'{category.name} | Emporium Plug Kenya',
            'page_meta_description': (
                category.description or
                f'Shop {category.name} from Emporium Plug in Kenya for S18 pickup or assisted town parcel arrangements.'
            )[:160],
            'page_heading': f'Shop {category.name}',
            'page_intro': category.description or f'Browse available {category.name} products from Emporium Plug.',
            'prevent_indexing': bool(self.request.GET),
        })
        return context
    
class ProductDetailPageView(TemplateView):
    """
    Public product page. Variants (if any) each carry their own live
    price (flash-sale aware) and stock total; simple products use
    Product.price / compare_at_price directly.
    """
    template_name = "core/product_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from inventory.models import Stock
        product = get_object_or_404(
            Product.objects.select_related('category').prefetch_related(
                'gallery_images', 'options__values', 'quantity_price_tiers',
                'variants__option_assignments__option',
                'variants__option_assignments__value',
            ),
            slug=kwargs['slug'],
            status=Product.Status.ACTIVE,
            category__is_visible=True,
        )
        variants = list(product.variants.filter(is_active=True))
        now = timezone.now()
        variant_data = []
        in_stock = False
        if variants:
            stock_queryset = Stock.objects.filter(
                variant_id__in=[v.id for v in variants],
            )
            stock_rows = stock_queryset.values('variant_id').annotate(
                total=Sum(F('quantity') - F('reserved_quantity'))
            )
            stock_map = {r['variant_id']: r['total'] for r in stock_rows}
            active_sales = {
                fs.variant_id: fs for fs in FlashSale.objects.filter(
                    variant__product=product, start_time__lte=now,
                    end_time__gte=now, is_active=True,
                )
            }
            for v in variants:
                fs = active_sales.get(v.id)
                stock_qty = stock_map.get(v.id, 0)
                if stock_qty > 0:
                    in_stock = True
                variant_data.append({
                    'variant': v,
                    'stock': stock_qty,
                    'price': fs.sale_price if fs else v.effective_price,
                    'flash_sale': fs,
                    'option_value_ids': [
                        assignment.value_id for assignment in v.option_assignments.all()
                    ],
                    'image_url': v.image.url if v.image else '',
                })
            variant_data.sort(key=lambda item: item['stock'] <= 0)
        else:
            direct_stock_queryset = Stock.objects.filter(
                product=product, variant__isnull=True,
            )
            direct_stock = direct_stock_queryset.aggregate(
                total=Sum(F('quantity') - F('reserved_quantity'))
            )['total'] or 0
            in_stock = direct_stock > 0
            context['direct_stock'] = direct_stock
        reviews_qs = product.reviews.filter(
            is_approved=True, is_current=True,
        ).select_related('customer')
        average_rating = reviews_qs.aggregate(avg=Avg('rating'))['avg']
        canonical_url = self.request.build_absolute_uri(
            reverse('core:product_detail', kwargs={'slug': product.slug}),
        )
        gallery_urls = [self.request.build_absolute_uri(image.image.url) for image in product.gallery_images.all()]
        if product.image:
            gallery_urls.insert(0, self.request.build_absolute_uri(product.image.url))
        overall_available = public_products().get(pk=product.pk).available_stock > 0
        offer_price = (
            min(item['price'] for item in variant_data)
            if variant_data else product.price
        )
        product_schema = {
            '@context': 'https://schema.org',
            '@type': 'Product',
            'name': product.name,
            'description': product.meta_description or product.description or product.name,
            'sku': product.sku,
            'brand': {'@type': 'Brand', 'name': 'Emporium Plug'},
            'url': canonical_url,
            'image': gallery_urls,
            'offers': {
                '@type': 'Offer',
                'priceCurrency': 'KES',
                'price': str(offer_price),
                'availability': (
                    'https://schema.org/InStock' if overall_available
                    else 'https://schema.org/OutOfStock'
                ),
                'url': canonical_url,
                'itemCondition': 'https://schema.org/NewCondition',
                'seller': {'@type': 'Organization', 'name': 'Emporium Plug'},
            },
        }
        review_count = reviews_qs.count()
        can_review = False
        review_submitted = False
        if self.request.user.is_authenticated and self.request.user.role == User.Role.CUSTOMER:
            review_submitted = ProductReview.objects.filter(
                product=product, customer=self.request.user, is_current=True,
            ).exists()
            can_review = (
                not review_submitted
                and FeedbackService._has_completed_purchase(product, self.request.user)
            )
        if average_rating is not None and review_count:
            product_schema['aggregateRating'] = {
                '@type': 'AggregateRating',
                'ratingValue': str(average_rating),
                'reviewCount': review_count,
            }
        context.update({
            'product': product,
            'variant_data': variant_data,
            'variant_matrix': [
                {
                    'id': item['variant'].pk,
                    'sku': item['variant'].sku,
                    'values': item['option_value_ids'],
                    'price': str(item['price']),
                    'stock': item['stock'],
                    'image': item['image_url'],
                    'image_alt': f"{product.name} — {item['variant'].option_summary}",
                    'flash_end': (
                        item['flash_sale'].end_time.isoformat()
                        if item['flash_sale'] else ''
                    ),
                }
                for item in variant_data
            ],
            'option_groups': product.options.prefetch_related('values').all(),
            'has_variants': bool(variants),
            'in_stock': in_stock,
            'on_sale': bool(product.compare_at_price and product.compare_at_price > product.price),
            'reviews': reviews_qs.order_by('-created_at')[:20],
            'average_rating': average_rating,
            'can_review': can_review,
            'review_submitted': review_submitted,
            'review_count': review_count,
            'is_wishlisted': product.pk in wishlist_product_ids(self.request),
            'canonical_url': canonical_url,
            'meta_description': (product.meta_description or product.description or product.name)[:160],
            'product_schema': product_schema,
            'related_products': public_products().filter(
                category=product.category,
            ).exclude(id=product.id)[:4],
            'restock_phone': (
                self.request.user.phone_number
                if self.request.user.is_authenticated else ''
            ),
            'quantity_price_tiers': product.quantity_price_tiers.filter(is_active=True),
        })
        manage_token = self.request.session.get('restock_manage_token')
        if manage_token:
            context['restock_manage_subscription'] = RestockSubscription.objects.filter(
                unsubscribe_token=manage_token,
                status=RestockSubscription.Status.ACTIVE,
            ).filter(
                Q(product=product) | Q(variant__product=product),
            ).first()
        cart = UnifiedSessionCartService(self.request)
        context.update({
            'cart_items': cart.get_cart_items_extended(),
            'cart_total': cart.get_total_financial_cost(),
            'cart_branch': Branch.objects.filter(pk=cart.cart_branch_id).first(),
        })
        return context


class StorefrontSitemapView(TemplateView):
    template_name = 'core/sitemap.xml'
    content_type = 'application/xml'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['home_url'] = self.request.build_absolute_uri(reverse('core:storefront_home'))
        context['products'] = public_products().order_by('pk')
        context['categories'] = visible_categories()
        context['static_urls'] = [
            self.request.build_absolute_uri(reverse('core:about')),
            self.request.build_absolute_uri(reverse('core:faq')),
            self.request.build_absolute_uri(reverse('core:delivery_pickup')),
            self.request.build_absolute_uri(reverse('core:returns_policy')),
            self.request.build_absolute_uri(reverse('core:terms')),
            self.request.build_absolute_uri(reverse('accounts:privacy')),
        ]
        return context


class RobotsPolicyView(View):
    def get(self, request):
        sitemap_url = request.build_absolute_uri(reverse('core:sitemap'))
        return HttpResponse(
            f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /management/\nDisallow: /accounts/profile/\n\n"
            f"User-agent: OAI-SearchBot\nAllow: /\n\nSitemap: {sitemap_url}\n",
            content_type='text/plain',
        )


class PointOfSaleWorkspaceTerminalView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Protects and renders the reactive, lightning-fast counter cashier interface.
    Enforces strict access control limits to verify staff assignments.
    """
    template_name = "core/pos_workspace.html"

    def test_func(self):
        # Only allow internal operators or managers to open the checkout terminal
        user = self.request.user
        return is_pos_operator(user)

    def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            # Binds user branch variables to lock down multi-tenant isolation barriers
            context['operator_branch'] = self.request.user.branch
            user = self.request.user
            from reports.reconciliation_services import POSShiftService
            context['current_pos_shift'] = POSShiftService.current_shift(user)
            if user.role in [User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN] and user.branch:
                from reports.models import ShiftReconciliation
                context['pending_reconciliations'] = ShiftReconciliation.objects.filter(
                    branch=user.branch,
                    requires_manager_review=True,
                    is_verified_by_manager=False,
                ).select_related('cashier').order_by('-closed_at')[:10]
            return context
    
class AnalyticsDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Renders the secure structural layout shell for the Management Dashboard.
    Injects configuration hooks and multi-branch filter dropdown contexts.
    """
    template_name = "core/dashboard.html"

    def test_func(self):
        # Enforce RBAC security matrix parameters
        return self.request.user.is_authenticated and self.request.user.role in [
            User.Role.BRANCH_MANAGER, 
            User.Role.SUPER_ADMIN
        ]

    def handle_no_permission(self):
        raise PermissionDenied("Access Denied: You do not possess the required management clearance level.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        from django.db.models import ExpressionWrapper, IntegerField
        from django.db.models.functions import Coalesce
        from inventory.models import TransferRequest
        from marketing.models import ProductReview, ReturnRequest
        from notifications.models import Notification
        from payments.models import MpesaTransaction
        from reports.models import POSShift, ShiftReconciliation
        from orders.models import OrderStatusHistory

        branches = Branch.objects.filter(is_active=True).order_by('name')
        selected_branch = user.branch
        if user.role == User.Role.SUPER_ADMIN:
            requested_branch = self.request.GET.get('branch')
            if requested_branch and requested_branch != 'all':
                selected_branch = branches.filter(pk=requested_branch).first()

        order_scope = Order.objects.all()
        stock_scope = Stock.objects.select_related('product', 'variant__product', 'branch')
        return_scope = ReturnRequest.objects.all()
        notification_scope = Notification.objects.all()
        payment_scope = MpesaTransaction.objects.select_related('order')
        transfer_scope = TransferRequest.objects.all()
        shift_scope = POSShift.objects.all()
        reconciliation_scope = ShiftReconciliation.objects.all()
        activity_scope = OrderStatusHistory.objects.select_related('order__branch', 'changed_by')
        if selected_branch is not None:
            order_scope = order_scope.filter(branch=selected_branch)
            stock_scope = stock_scope.filter(branch=selected_branch)
            return_scope = return_scope.filter(order__branch=selected_branch)
            notification_scope = notification_scope.filter(branch=selected_branch)
            payment_scope = payment_scope.filter(order__branch=selected_branch)
            transfer_scope = transfer_scope.filter(Q(from_branch=selected_branch) | Q(to_branch=selected_branch))
            shift_scope = shift_scope.filter(branch=selected_branch)
            reconciliation_scope = reconciliation_scope.filter(branch=selected_branch)
            activity_scope = activity_scope.filter(order__branch=selected_branch)

        active_order_statuses = [
            Order.Status.PENDING, Order.Status.PAYMENT_CONFIRMED, Order.Status.PROCESSING,
            Order.Status.PACKING, Order.Status.PACKED, Order.Status.RIDER_ASSIGNED,
            Order.Status.DISPATCHED, Order.Status.ARRIVED_AT_DESTINATION,
            Order.Status.OUT_FOR_DELIVERY, Order.Status.READY_FOR_PICKUP,
            Order.Status.DISPUTED,
        ]
        low_stock_count = stock_scope.annotate(
            available_units=ExpressionWrapper(
                F('quantity') - F('reserved_quantity'), output_field=IntegerField(),
            ),
            alert_threshold=Coalesce(
                'product__low_stock_threshold', 'variant__product__low_stock_threshold',
            ),
        ).filter(available_units__lte=F('alert_threshold')).count()
        active_orders = order_scope.filter(
            order_type__in=[Order.OrderType.ONLINE_DELIVERY, Order.OrderType.ONLINE_PICKUP],
            status__in=active_order_statuses,
        ).count()
        pending_returns = return_scope.filter(status=ReturnRequest.ReturnStatus.PENDING).count()
        attention = [
            {'label': 'Orders awaiting fulfilment', 'count': active_orders,
             'url': reverse('logistics:fulfilment-workspace'),
             'help': 'Orders that have not reached a final customer handover state.', 'tone': 'blue'},
            {'label': 'Low-stock lines', 'count': low_stock_count,
             'url': reverse('inventory:inventory-workspace'),
             'help': 'Available branch stock at or below the product threshold.', 'tone': 'orange'},
            {'label': 'Returns pending review', 'count': pending_returns,
             'url': reverse('marketing:operations-workspace'),
             'help': 'Return requests awaiting a manager decision and stock-condition outcome.', 'tone': 'blue'},
            {'label': 'Payments needing reconciliation',
             'count': payment_scope.filter(status=MpesaTransaction.Status.RECONCILIATION_REQUIRED).count(),
             'url': reverse('admin:payments_mpesatransaction_changelist') if user.is_superuser else reverse('report_workspace:operations'),
             'help': 'Payment evidence that did not match automatically and requires review.', 'tone': 'orange'},
        ]
        context.update({
            'is_super_admin': user.role == User.Role.SUPER_ADMIN,
            'branches': branches,
            'selected_branch': selected_branch,
            'scope_label': selected_branch.name if selected_branch else 'All branches',
            'attention': attention,
            'summary': {
                'active_orders': active_orders, 'low_stock': low_stock_count,
                'open_shifts': shift_scope.filter(status=POSShift.Status.OPEN).count(),
                'pending_returns': pending_returns,
            },
            'secondary_attention': {
                'transfers': transfer_scope.filter(status__in=[
                    TransferRequest.Status.APPROVED, TransferRequest.Status.DISPATCHED,
                    TransferRequest.Status.PARTIALLY_RECEIVED,
                ]).count(),
                'notifications': notification_scope.filter(status=Notification.Status.MANUAL_FOLLOWUP).count(),
                'shift_reviews': reconciliation_scope.filter(
                    requires_manager_review=True, is_verified_by_manager=False,
                ).count(),
                'reviews': ProductReview.objects.filter(is_current=True, moderated_at__isnull=True).count(),
            },
            'recent_activity': activity_scope.order_by('-created_at')[:10],
        })
        return context


class AnalyticsDashboardMetricsPartialView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Asynchronous HTMX partial view generating high-performance analytical aggregates
    and tracking trends wrapped in transactional security scopes.
    """
    template_name = "core/partials/dashboard_metrics.html"

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in [
            User.Role.BRANCH_MANAGER, 
            User.Role.SUPER_ADMIN
        ]


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        timeframe = self.request.GET.get('timeframe', '7_days')
        if timeframe not in ('today', '7_days', '30_days'):
            timeframe = '7_days'

        # Multi-branch isolation: managers locked to own branch; super
        # admin gets branch=None (system-wide) unless branch_filter_id set.
        target_branch = None
        if user.role == User.Role.BRANCH_MANAGER:
            target_branch = user.branch
        elif user.role == User.Role.SUPER_ADMIN:
            filter_id = self.request.GET.get('branch_filter_id')
            if filter_id and filter_id != "ALL":
                target_branch = Branch.objects.filter(id=filter_id).first()

        from reports.shift_services import ShiftReportService
        context.update(
            ShiftReportService.get_dashboard_metrics(branch=target_branch, period=timeframe)
        )
        return context
    

class AsynchronousPOSProductLookupView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Executes real-time search-as-you-type product variant matches.
    Optimized with text indexing fields to prevent bottleneck lag under heavy checkout load.
    """
    def test_func(self):
        return is_pos_operator(self.request.user)

    def get(self, request, *args, **kwargs):
        query_string = request.GET.get('q', '').strip()
        if len(query_string) < 2:
            return HttpResponse('<div class="text-xs text-gray-400 p-3 italic">Enter at least 2 characters to trigger catalog scanning lookup...</div>')

        # Fast lookup targeting primary item names, unique system SKUs, or custom attributes
        branch_stocks = Stock.objects.filter(
            branch=request.user.branch,
            quantity__gt=F('reserved_quantity'),
        )
        variant_stock = {row.variant_id: row for row in branch_stocks.filter(variant__isnull=False)}
        product_stock = {row.product_id: row for row in branch_stocks.filter(product__isnull=False)}
        matched_variants = list(ProductVariant.objects.select_related('product', 'product__category').filter(
            Q(product__status=Product.Status.ACTIVE) & (
                Q(product__name__icontains=query_string) | 
                Q(product__sku__icontains=query_string) | 
                Q(attribute_value__icontains=query_string)
            ),
            id__in=variant_stock,
        )[:12])
        matched_products = list(Product.objects.filter(
            id__in=product_stock,
            status=Product.Status.ACTIVE,
            variants__isnull=True,
        ).filter(
            Q(name__icontains=query_string) | Q(sku__icontains=query_string)
        )[:12])
        for variant in matched_variants:
            variant.pos_available = variant_stock[variant.pk].available_quantity
        for product in matched_products:
            product.pos_available = product_stock[product.pk].available_quantity

        return render(request, 'core/partials/pos_search_results.html', {
            'variants': matched_variants,
            'products': matched_products,
        })


class ReactivePOSCartActionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Mutates item quantities inside the cashier's session-isolated memory tray.
    Broadcasts state signals back to keep layout counters aligned.
    """
    def test_func(self):
        return is_pos_operator(self.request.user)
    def get(self, request, *args, **kwargs):
        cart_service = UnifiedPOSCartService(request)
        cart_items = cart_service.get_cart_items_extended()
        total_cost = cart_service.get_total_financial_cost()
        item_count = cart_service.get_total_item_count()

        context = {
            'cart_items': cart_items,
            'pos_items': cart_items,
            'total_cost': total_cost,
            'pos_total': total_cost,
            'item_count': item_count,
            'pos_count': item_count,
        }
        return render(request, 'core/partials/pos_cart_tray.html', context)


    def post(self, request, *args, **kwargs):
        cart_service = UnifiedPOSCartService(request)
        variant_id = request.POST.get('variant_id')
        product_id = request.POST.get('product_id')
        action_type = request.POST.get('action')
        raw_quantity = request.POST.get('quantity', '1')

        try:
            parsed_quantity = int(raw_quantity)
            quantity = max(0 if action_type == 'update' else 1, parsed_quantity)
        except ValueError:
            quantity = 1

        if product_id:
            item_key = f"p:{product_id}"
        elif variant_id:
            item_key = str(variant_id)
        else:
            item_key = None
            
        operation_ok = True
        if action_type == 'add':
            if product_id:
                operation_ok = cart_service.add_product_item(product_id, quantity=1, override_quantity=False)
            elif variant_id:
                operation_ok = cart_service.add_item(variant_id, quantity=1, override_quantity=False)

        elif action_type == 'update':
            if product_id:
                operation_ok = cart_service.add_product_item(product_id, quantity=quantity, override_quantity=True)
            elif variant_id:
                operation_ok = cart_service.add_item(variant_id, quantity=quantity, override_quantity=True)

        elif action_type == 'remove':
            if item_key:
                cart_service.remove_item(item_key)

        elif action_type == 'clear':
            cart_service.flush_entire_cart()


        context = {
            'cart_items': cart_service.get_cart_items_extended(),
            'pos_items': cart_service.get_cart_items_extended(),
            'total_cost': cart_service.get_total_financial_cost(),
            'pos_total': cart_service.get_total_financial_cost(),
            'item_count': cart_service.get_total_item_count(),
            'pos_count': cart_service.get_total_item_count()
        }
        if not operation_ok:
            context['cart_error'] = 'Quantity exceeds available stock at this branch.'
        
        response = render(request, 'core/partials/pos_cart_tray.html', context)
        response['HX-Trigger'] = 'update-navbar-cart-count'
        return response


class POSCustomerDisplayView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Read-only customer screen backed by the operator's current session cart."""

    template_name = 'core/pos_customer_display.html'

    def test_func(self):
        return is_pos_operator(self.request.user)


class POSCustomerDisplayPartialView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return is_pos_operator(self.request.user)

    def get(self, request, *args, **kwargs):
        cart = UnifiedPOSCartService(request)
        return render(request, 'core/partials/pos_customer_display.html', {
            'items': cart.get_cart_items_extended(),
            'total': cart.get_total_financial_cost(),
        })


class POSOrderCheckoutSubmissionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Validates transactional parameters, processes optional manager authorization credentials, 
    and executes atomic state deductions.
    """
    def test_func(self):
        return is_pos_operator(self.request.user)

    def post(self, request, *args, **kwargs):
        cart_service = UnifiedPOSCartService(request)
        extended_items = cart_service.get_cart_items_extended()
        cashier_profile = request.user

        if not cashier_profile.branch and cashier_profile.role == User.Role.SUPER_ADMIN:
            return HttpResponse(
                '<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">Refusal: Super Admin profiles must assign an active target Branch context before checkout execution.</div>',
                status=400
            )

        if not extended_items:
            return HttpResponse(
                '<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">Refusal: Action blocked because product tray is completely empty.</div>', 
                status=400
            )

        customer_phone = request.POST.get('customer_phone', '').strip()
        payment_method = request.POST.get('payment_method', Order.PaymentMethod.CASH)
        payment_reference = request.POST.get('payment_reference', '').strip() or None
        amount_received = request.POST.get('amount_received', '').strip() or None
        raw_discount = request.POST.get('discount_amount', '0.00')

        try:
            discount_amount = Decimal(raw_discount)
        except Exception:
            discount_amount = Decimal('0.00')
        manager_identity = request.POST.get('manager_username') or request.POST.get('manager_override_username')
        manager_secret = request.POST.get('manager_password') or request.POST.get('manager_override_password')
        authorized_manager = None

        if discount_amount > 0:
            try:
                authorized_manager = POSSalesService.authorize_discount_override(
                    manager_username=manager_identity,
                    manager_password=manager_secret,
                    requesting_cashier=cashier_profile,
                    ip_address=request.META.get('REMOTE_ADDR'),
                )
            except ValidationError as e:
                if getattr(e, 'code', None) == 'branch_mismatch':
                    return HttpResponse(
                        f'<div class="rounded-md bg-amber-50 p-3 text-sm text-amber-800 border border-amber-200 font-medium">'
                        f'Bypass Failure: {e.message}</div>',
                        status=403,
                    )
                return HttpResponseForbidden(f"Security Fault / Bypass Failure: {e.message}")

        if payment_method == Order.PaymentMethod.PAYBILL and authorized_manager is None:
            try:
                from analytics.models import AuditLog
                authorized_manager = POSSalesService._authorize_manager_credentials(
                    manager_username=manager_identity,
                    manager_password=manager_secret,
                    requesting_cashier=cashier_profile,
                    action_type=AuditLog.ActionTypes.MANUAL_PAYMENT_CONFIRMATION,
                    context_label='a walk-in Paybill payment verification',
                    ip_address=request.META.get('REMOTE_ADDR'),
                )
            except ValidationError as error:
                return HttpResponseForbidden(
                    f"Payment verification refused: {error.messages[0]}"
                )
        # Assemble structural line item payload arrays
        items_payload = [{
            'variant': line.get('variant'),
            'product': line.get('product') if not line.get('variant') else None,
            'quantity': line['quantity']
        } for line in extended_items]


        try:
            from reports.reconciliation_services import POSShiftService
            current_shift = POSShiftService.current_shift(request.user)
            completed_order = POSSalesService.process_walk_in_sale(
                branch=request.user.branch,
                cashier=request.user,
                customer_phone=customer_phone,
                items_payload=items_payload,
                discount_amount=discount_amount,
                payment_method=payment_method,
                payment_reference=payment_reference,
                amount_received=amount_received,
                manager_authorized_by=authorized_manager,
                payment_verification_reason=request.POST.get(
                    'payment_verification_reason', ''
                ).strip(),
                pos_shift=current_shift,
                discount_reason=request.POST.get('discount_reason', '').strip(),
                coupon_code=request.POST.get('coupon_code', '').strip() or None,
            )
            # Flush current terminal context rows
            cart_service.flush_entire_cart()
            change_html = ''
            if completed_order.change_due is not None:
                change_html = (
                    f'<div class="mt-2 font-bold">Change due: KES '
                    f'{completed_order.change_due}</div>'
                )
            receipt_url = reverse('order-receipt-pdf', args=[completed_order.pk])
            response = HttpResponse(
                f'<div class="rounded-md bg-green-50 p-4 text-sm font-bold text-green-800 border border-green-200 shadow-sm">'
                f'Transaction complete. Reference number: {completed_order.order_number}</div>'
                f'{change_html}'
                f'<div class="mt-3 flex gap-4">'
                f'<a class="inline-block underline" href="{receipt_url}">Download receipt</a>'
                f'<a class="inline-block underline" href="{reverse("core:pos_workspace")}">Start a new sale</a>'
                f'</div>'
            )
            # Remove the transactional controls immediately after a successful
            # commit so an impatient second click cannot create a duplicate sale.
            response['HX-Retarget'] = '#pos-tray-wrapper'
            response['HX-Reswap'] = 'innerHTML'
            response['HX-Trigger'] = 'update-navbar-cart-count'
            return response
        except ValidationError as error_trace:
            return HttpResponse(
                f'<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">'
                f'Execution Defended: {error_trace.message if hasattr(error_trace, "message") else str(error_trace)}</div>',
                status=400
            )
        
class POSVoidSaleView(LoginRequiredMixin, UserPassesTestMixin, View):
    """POST /pos-desk/void/<order_number>/ -- void a COMPLETED walk-in sale under manager PIN."""

    def test_func(self):
        return is_pos_operator(self.request.user)

    def post(self, request, order_number, *args, **kwargs):
        if not request.user.branch and request.user.role == User.Role.SUPER_ADMIN:
            return HttpResponse(
                '<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">'
                'Refusal: Super Admin profiles must assign an active target Branch context before voiding.</div>',
                status=400,
            )

        try:
            voided_order = POSSalesService.void_sale(
                order_number=order_number,
                branch=request.user.branch,
                requesting_staff=request.user,
                manager_username=request.POST.get('manager_username'),
                manager_password=request.POST.get('manager_password'),
                void_reason=request.POST.get('void_reason', ''),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            return HttpResponse(
                f'<div class="rounded-md bg-amber-50 p-4 text-sm font-bold text-amber-800 border border-amber-200 shadow-sm">'
                f'✓ Order {voided_order.order_number} voided. Stock restored.</div>'
            )
        except ValidationError as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            status_code = 403 if getattr(e, 'code', None) in ('invalid_credentials', 'branch_mismatch') else 400
            return HttpResponse(
                f'<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">'
                f'{error_msg}</div>',
                status=status_code,
            )
        
class ShiftOpenSubmissionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """POST /pos-desk/shift/open/ — begin one branch-scoped cashier shift."""

    def test_func(self):
        return is_pos_operator(self.request.user)

    def post(self, request, *args, **kwargs):
        from reports.reconciliation_services import POSShiftService
        try:
            shift, created = POSShiftService.open_shift(
                cashier=request.user,
                opening_cash=request.POST.get('opening_cash', '0.00'),
            )
        except ValidationError as exc:
            return HttpResponse(
                f'<div class="rounded-md bg-red-50 p-3 text-sm text-red-800">{exc.messages[0]}</div>',
                status=400,
            )
        message = 'Shift opened.' if created else 'Your shift is already open.'
        return HttpResponse(
            f'<div class="rounded-md bg-green-50 p-3 text-sm font-bold text-green-800">'
            f'{message} Opening cash: KES {shift.opening_cash:,.2f}. Refreshing…</div>'
            '<script>setTimeout(() => window.location.reload(), 700);</script>'
        )


class ShiftCloseSubmissionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """POST /pos-desk/shift/close/ -- cashier counts drawer, submits actual cash on hand."""
    def test_func(self):
        return is_pos_operator(self.request.user)
    def post(self, request, *args, **kwargs):
        from reports.reconciliation_services import ShiftReconciliationService, CASH_VARIANCE_ALERT_THRESHOLD
        raw_actual = request.POST.get('actual_cash', '').strip()
        try:
            actual_cash = Decimal(raw_actual)
        except Exception:
            return HttpResponse(
                '<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">Please enter a valid amount.</div>',
                status=400,
            )
        try:
            reconciliation = ShiftReconciliationService.close_shift(
                cashier=request.user, actual_cash=actual_cash,
                notes=request.POST.get('notes', ''),
            )
        except ValidationError as e:
            return HttpResponse(
                f'<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">'
                f'{e.message if hasattr(e, "message") else str(e)}</div>',
                status=400,
            )
        variance = reconciliation.cash_variance
        if variance == 0:
            response = HttpResponse(
                '<div class="rounded-md bg-green-50 p-4 text-sm font-bold text-green-800 border border-green-200">'
                'Your drawer matches exactly. Shift closed.</div>'
            )
            response['HX-Refresh'] = 'true'
            return response
        direction = 'more' if variance > 0 else 'less'
        flagged_note = " Your manager has been notified to double-check with you." if abs(variance) > CASH_VARIANCE_ALERT_THRESHOLD else ""
        response = HttpResponse(
            f'<div class="rounded-md bg-amber-50 p-4 text-sm font-bold text-amber-800 border border-amber-200">'
            f'Shift closed. You counted KES {abs(variance):,.2f} {direction} than expected '
            f'(expected KES {reconciliation.expected_cash:,.2f}, you counted KES {reconciliation.actual_cash:,.2f}).'
            f'{flagged_note}</div>'
        )
        response['HX-Refresh'] = 'true'
        return response
class ShiftVerifySubmissionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """POST /pos-desk/shift/<id>/verify/ -- manager confirms a flagged reconciliation was checked."""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in [
            User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN,
        ]
    def post(self, request, reconciliation_id, *args, **kwargs):
        from reports.reconciliation_services import ShiftReconciliationService
        try:
            ShiftReconciliationService.verify_reconciliation(
                reconciliation_id=reconciliation_id,
                manager=request.user,
                reason=request.POST.get('verification_reason', ''),
            )
        except ValidationError as e:
            return HttpResponse(
                f'<div class="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-800 border border-red-200">'
                f'{e.message if hasattr(e, "message") else str(e)}</div>',
                status=400,
            )
        return HttpResponse(
            '<div class="rounded-md bg-emerald-50 p-3 text-xs font-bold text-emerald-800 border border-emerald-200">✓ Reviewed</div>'
        )
