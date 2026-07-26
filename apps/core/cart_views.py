# apps/core/cart_views.py
# v3 — implements suggestions 1-4 from review:
#   1. quantity > 0 validated in Add view only (Update keeps <=0 = remove)
#   2. json.JSONDecodeError used instead of bare ValueError
#   3. logger actually used at every rejection point
#   4. repeated JSON parsing extracted into _parse_json_body() helper

import json
import logging
from django.http import JsonResponse
from django.views import View

from orders.cart_services import UnifiedSessionCartService
from branches.models import Branch

logger = logging.getLogger(__name__)


def _parse_json_body(request):
    """
    Shared JSON body parser for all cart views.
    Returns (data, None) on success, or (None, JsonResponse) on failure --
    caller does `data, error = _parse_json_body(request); if error: return error`.
    """
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Cart view received invalid JSON body: {e}")
        return None, JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)


class StorefrontCartDetailView(View):
    """GET /cart/ — returns current cart contents as JSON."""

    def get(self, request):
        cart = UnifiedSessionCartService(request)
        items = cart.get_cart_items_extended()
        branch = Branch.objects.filter(pk=cart.cart_branch_id).first()
        return JsonResponse({
            'items': [
                {
                    'key': item['key'],
                    'type': item['type'],
                    'name': item['name'],
                    'sku': item['sku'],
                    'quantity': item['quantity'],
                    'price': str(item['price']),
                    'total_price': str(item['total_price']),
                    'product_id': str(item['product'].id) if item['product'] else None,
                    'variant_id': str(item['variant'].id) if item['variant'] else None,
                }
                for item in items
            ],
            'total': str(cart.get_total_financial_cost()),
            'item_count': cart.get_total_item_count(),
            'is_empty': cart.is_empty(),
            'branch_id': branch.pk if branch else None,
            'branch_name': branch.name if branch else None,
        })


class StorefrontAddToCartView(View):
    """
    POST /cart/add/
    Body: {'type': 'variant'|'product', 'id': '<uuid>', 'quantity': 1}
    """

    def post(self, request):
        body, error = _parse_json_body(request)
        if error:
            return error

        item_type = body.get('type')
        item_id = body.get('id')

        try:
            quantity = int(body.get('quantity', 1))
        except (ValueError, TypeError):
            logger.warning(f"Add-to-cart rejected: non-numeric quantity {body.get('quantity')!r}")
            return JsonResponse(
                {'success': False, 'error': 'quantity must be a whole number.'},
                status=400,
            )

        # Suggestion 1: quantity must be positive to ADD. This does not
        # apply to the Update view, where <=0 intentionally means "remove".
        if quantity <= 0:
            logger.warning(f"Add-to-cart rejected: non-positive quantity {quantity}")
            return JsonResponse(
                {'success': False, 'error': 'quantity must be greater than zero.'},
                status=400,
            )

        if not item_type or not item_id:
            logger.warning("Add-to-cart rejected: missing type or id.")
            return JsonResponse(
                {'success': False, 'error': 'type and id are required.'},
                status=400,
            )

        cart = UnifiedSessionCartService(request)

        if item_type == 'variant':
            result = cart.add_variant(variant_id=item_id, quantity=quantity)
        elif item_type == 'product':
            result = cart.add_product(product_id=item_id, quantity=quantity)
        else:
            logger.warning(f"Add-to-cart rejected: unknown type {item_type!r}")
            return JsonResponse(
                {'success': False, 'error': 'type must be variant or product.'},
                status=400,
            )

        if not result.get('success'):
            logger.warning(f"Add-to-cart failed for {item_type} {item_id}: {result.get('error')}")

        result['item_count'] = cart.get_total_item_count()
        result['total'] = str(cart.get_total_financial_cost())
        return JsonResponse(result)


class StorefrontUpdateCartView(View):
    """
    POST /cart/update/
    Body: {'key': 'v:<uuid>', 'quantity': 3}
    NOTE: quantity <= 0 is intentionally valid here -- it means "remove
    this item", per UnifiedSessionCartService.update_quantity(). Do not
    add a positive-only check here like the Add view has.
    """

    def post(self, request):
        body, error = _parse_json_body(request)
        if error:
            return error

        cart_key = body.get('key')
        raw_quantity = body.get('quantity')

        if not cart_key or raw_quantity is None:
            logger.warning("Update-cart rejected: missing key or quantity.")
            return JsonResponse(
                {'success': False, 'error': 'key and quantity are required.'},
                status=400,
            )

        try:
            quantity = int(raw_quantity)
        except (ValueError, TypeError):
            logger.warning(f"Update-cart rejected: non-numeric quantity {raw_quantity!r}")
            return JsonResponse(
                {'success': False, 'error': 'quantity must be a whole number.'},
                status=400,
            )

        cart = UnifiedSessionCartService(request)
        result = cart.update_quantity(cart_key, quantity)

        if isinstance(result, dict):
            if not result.get('success'):
                logger.warning(f"Update-cart failed for key {cart_key}: {result.get('error')}")
            result['item_count'] = cart.get_total_item_count()
            result['total'] = str(cart.get_total_financial_cost())
            return JsonResponse(result)

        return JsonResponse({
            'success': result,
            'item_count': cart.get_total_item_count(),
            'total': str(cart.get_total_financial_cost()),
        })


class StorefrontRemoveFromCartView(View):
    """POST /cart/remove/ — Body: {'key': 'v:<uuid>'}"""

    def post(self, request):
        body, error = _parse_json_body(request)
        if error:
            return error

        cart_key = body.get('key')
        if not cart_key:
            logger.warning("Remove-from-cart rejected: missing key.")
            return JsonResponse({'success': False, 'error': 'key is required.'}, status=400)

        cart = UnifiedSessionCartService(request)
        removed = cart.remove_item(cart_key)

        if not removed:
            logger.warning(f"Remove-from-cart: key {cart_key} was not found in cart.")

        return JsonResponse({
            'success': removed,
            'item_count': cart.get_total_item_count(),
            'total': str(cart.get_total_financial_cost()),
        })
