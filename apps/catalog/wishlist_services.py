from django.db import transaction

from .models import Product, WishlistItem


WISHLIST_SESSION_KEY = 'storefront_wishlist_product_ids'
MAX_GUEST_WISHLIST_ITEMS = 100


def _session_ids(request):
    raw_ids = request.session.get(WISHLIST_SESSION_KEY, [])
    valid_ids = []
    for value in raw_ids if isinstance(raw_ids, list) else []:
        try:
            product_id = int(value)
        except (TypeError, ValueError):
            continue
        if product_id > 0 and product_id not in valid_ids:
            valid_ids.append(product_id)
    return valid_ids[:MAX_GUEST_WISHLIST_ITEMS]


def wishlist_product_ids(request):
    if request.user.is_authenticated and getattr(request.user, 'role', None) == 'CUSTOMER':
        return set(WishlistItem.objects.filter(customer=request.user).values_list('product_id', flat=True))
    return set(_session_ids(request))


def toggle_wishlist_product(request, product):
    """Toggle a product without affecting stock, cart contents, or price."""
    if request.user.is_authenticated and getattr(request.user, 'role', None) == 'CUSTOMER':
        item, created = WishlistItem.objects.get_or_create(
            customer=request.user,
            product=product,
        )
        if not created:
            item.delete()
        return created

    product_ids = _session_ids(request)
    if product.pk in product_ids:
        product_ids.remove(product.pk)
        saved = False
    else:
        if len(product_ids) >= MAX_GUEST_WISHLIST_ITEMS:
            product_ids.pop(0)
        product_ids.append(product.pk)
        saved = True
    request.session[WISHLIST_SESSION_KEY] = product_ids
    request.session.modified = True
    return saved


@transaction.atomic
def merge_guest_wishlist(request, customer):
    """Move the current guest list into the signed-in customer's list idempotently."""
    product_ids = _session_ids(request)
    existing_ids = set(Product.objects.filter(pk__in=product_ids).values_list('pk', flat=True))
    WishlistItem.objects.bulk_create(
        [WishlistItem(customer=customer, product_id=product_id) for product_id in existing_ids],
        ignore_conflicts=True,
    )
    request.session.pop(WISHLIST_SESSION_KEY, None)
    request.session.modified = True
