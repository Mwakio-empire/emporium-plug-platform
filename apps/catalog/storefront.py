from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.db.models import F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from branches.models import Branch
from inventory.models import Stock

from .models import Category, Product
from .constants import STOREFRONT_SELECTED_BRANCH_KEY


SORT_OPTIONS = {
    'newest': '-created_at',
    'price_asc': 'price',
    'price_desc': '-price',
    'name': 'name',
    'best_selling': '-sales_quantity',
}

FULFILLED_SALES_STATUSES = ('COMPLETED', 'DELIVERED', 'COLLECTED')
BEST_SELLING_WINDOW_DAYS = 90


def public_visible_category_ids():
    """Return categories whose complete ancestor path is publicly visible."""
    rows = list(Category.objects.values('id', 'parent_id', 'is_visible'))
    children_by_parent = {}
    for row in rows:
        children_by_parent.setdefault(row['parent_id'], []).append(row)

    visible_ids = set()
    frontier = [row for row in children_by_parent.get(None, []) if row['is_visible']]
    while frontier:
        category = frontier.pop()
        if category['id'] in visible_ids:
            continue
        visible_ids.add(category['id'])
        frontier.extend(
            child for child in children_by_parent.get(category['id'], [])
            if child['is_visible']
        )
    return visible_ids


def visible_categories():
    return Category.objects.filter(
        pk__in=public_visible_category_ids(),
    ).select_related('parent').order_by('name')


def active_branches():
    return Branch.objects.filter(is_active=True).order_by('name')


def select_storefront_branch(request, raw_branch_id):
    if raw_branch_id in (None, ''):
        request.session.pop(STOREFRONT_SELECTED_BRANCH_KEY, None)
        request.session.modified = True
        return None
    try:
        branch_id = int(raw_branch_id)
    except (TypeError, ValueError):
        return None
    branch = active_branches().filter(pk=branch_id).first()
    if branch is None:
        return None
    request.session[STOREFRONT_SELECTED_BRANCH_KEY] = branch.pk
    request.session.modified = True
    return branch


def _available_stock_subqueries(branch_id=None):
    direct = Stock.objects.filter(
        product=OuterRef('pk'), variant__isnull=True,
    )
    variants = Stock.objects.filter(variant__product=OuterRef('pk'))
    if branch_id is not None:
        direct = direct.filter(branch_id=branch_id)
        variants = variants.filter(branch_id=branch_id)
    direct = direct.values('product').annotate(
        total=Sum(F('quantity') - F('reserved_quantity')),
    ).values('total')
    variants = variants.values('variant__product').annotate(
        total=Sum(F('quantity') - F('reserved_quantity')),
    ).values('total')
    return direct, variants


def public_products(branch_id=None):
    direct, variants = _available_stock_subqueries(branch_id)
    return Product.objects.filter(
        status=Product.Status.ACTIVE,
        category_id__in=public_visible_category_ids(),
    ).select_related('category').prefetch_related('variants').annotate(
        direct_available=Coalesce(
            Subquery(direct, output_field=IntegerField()), Value(0),
        ),
        variant_available=Coalesce(
            Subquery(variants, output_field=IntegerField()), Value(0),
        ),
    ).annotate(
        available_stock=F('direct_available') + F('variant_available'),
    )


def annotate_recent_fulfilled_sales(queryset):
    from orders.models import OrderItem

    cutoff = timezone.now() - timedelta(days=BEST_SELLING_WINDOW_DAYS)
    eligible = {
        'order__status__in': FULFILLED_SALES_STATUSES,
        'order__created_at__gte': cutoff,
    }
    direct_sales = OrderItem.objects.filter(
        product=OuterRef('pk'), **eligible,
    ).values('product').annotate(total=Sum('quantity')).values('total')
    variant_sales = OrderItem.objects.filter(
        variant__product=OuterRef('pk'), **eligible,
    ).values('variant__product').annotate(total=Sum('quantity')).values('total')
    return queryset.annotate(
        direct_sales_quantity=Coalesce(
            Subquery(direct_sales, output_field=IntegerField()), Value(0),
        ),
        variant_sales_quantity=Coalesce(
            Subquery(variant_sales, output_field=IntegerField()), Value(0),
        ),
    ).annotate(
        sales_quantity=F('direct_sales_quantity') + F('variant_sales_quantity'),
    )


def category_and_descendant_ids(category_id):
    visible = Category.objects.filter(pk__in=public_visible_category_ids())
    if not visible.filter(pk=category_id).exists():
        return []
    discovered = {int(category_id)}
    frontier = {int(category_id)}
    while frontier:
        children = set(visible.filter(parent_id__in=frontier).values_list('id', flat=True))
        frontier = children - discovered
        discovered.update(frontier)
    return list(discovered)


def apply_storefront_filters(queryset, params):
    search = params.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(sku__icontains=search)
            | Q(category__name__icontains=search)
        )

    category_id = params.get('category', '').strip()
    if category_id:
        try:
            category_ids = category_and_descendant_ids(int(category_id))
        except (TypeError, ValueError):
            category_ids = []
        queryset = queryset.filter(category_id__in=category_ids)

    for parameter, lookup in (('min_price', 'price__gte'), ('max_price', 'price__lte')):
        raw_value = params.get(parameter, '').strip()
        if raw_value:
            try:
                value = Decimal(raw_value)
            except InvalidOperation:
                continue
            if value >= 0:
                queryset = queryset.filter(**{lookup: value})

    availability = params.get('availability', '').strip()
    if availability == 'in_stock':
        queryset = queryset.filter(available_stock__gt=0)
    elif availability == 'out_of_stock':
        queryset = queryset.filter(available_stock__lte=0)

    sort_option = params.get('sort', 'newest')
    if sort_option == 'best_selling':
        queryset = annotate_recent_fulfilled_sales(queryset)
    ordering = SORT_OPTIONS.get(sort_option, SORT_OPTIONS['newest'])
    return queryset.order_by(ordering, 'pk')
