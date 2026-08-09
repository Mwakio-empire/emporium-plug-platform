# apps/core/cart_services.py
# v3 — implements approved suggestions ① and ② on top of the 7 model-field
# fixes already applied in v2:
#   ① Sum() aggregation replaces Python sum() in add_variant, add_product,
#      and revalidate_stock stock checks
#   ② get_cart_items_extended() now self-heals stale entries (removes them
#      from the session) instead of leaving orphaned data forever
# Suggestions ③ and ④ (stock caching, bulk lookup) deferred per agreed
# prioritization -- not needed at current scale, revisit in Phase 3/4.

import logging
from copy import deepcopy
from decimal import Decimal
from django.db.models import Prefetch, Sum
from catalog.models import ProductVariant, Product
from catalog.models import QuantityPriceTier
from catalog.pricing import QuantityPricingService
from catalog.constants import STOREFRONT_SELECTED_BRANCH_KEY


def _available_total(queryset):
    balances = queryset.aggregate(
        on_hand=Sum('quantity'),
        reserved=Sum('reserved_quantity'),
    )
    return (balances['on_hand'] or 0) - (balances['reserved'] or 0)

def _resolve_display_price(variant):
    """
    Storefront cart must charge the live flash-sale price, not the static
    variant.effective_price — otherwise FlashSale only affects display,
    never the amount actually charged (spec §13 flash-sale requirement).
    Falls back to effective_price if PromotionService import fails for
    any reason (e.g. during app-loading edge cases) — never blocks cart ops.
    """
    try:
        from marketing.services import PromotionService
        return PromotionService.resolve_live_variant_market_price(variant)
    except Exception:
        return variant.effective_price
logger = logging.getLogger(__name__)

_POS_CART_KEY = 'dnt_pos_cart'
STOREFRONT_CART_KEY = 'dnt_storefront_cart'
STOREFRONT_CART_BRANCH_KEY = 'dnt_storefront_cart_branch_id'


class UnifiedPOSCartService:
    """Walk-in POS cart — cashier's active transaction tray."""

    def __init__(self, request):
        self.session = request.session
        self.branch = getattr(request.user, 'branch', None)
        cart = self.session.get(_POS_CART_KEY)
        if not cart:
            cart = self.session[_POS_CART_KEY] = {}
        self.cart = cart

    def add_product_item(self, product_id, quantity=1, override_quantity=False):
        """
        Adds a simple (non-variant) Product to the POS tray.
        Mirrors add_item()'s behavior exactly, for a Product instead
        of a ProductVariant.
        """
        from catalog.models import Product
        product_id_str = f"p:{product_id}"
 
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            logger.error(f"POS Cart: Product {product_id} not found.")
            return False

        stock = product.stocks.filter(branch=self.branch).first()
        current = self.cart.get(product_id_str, {}).get('quantity', 0)
        target = quantity if override_quantity else current + quantity
        if stock is None or target > stock.available_quantity:
            return False
 
        if product_id_str not in self.cart:
            self.cart[product_id_str] = {
                'type': 'product',
                'quantity': 0,
                'price': str(product.price),
                'name': product.name,
            }
 
        if override_quantity:
            self.cart[product_id_str]['quantity'] = quantity
        else:
            self.cart[product_id_str]['quantity'] += quantity
 
        if self.cart[product_id_str]['quantity'] <= 0:
            self.remove_item(product_id_str)
        else:
            self._save()
        return True

    def add_item(self, variant_id, quantity=1, override_quantity=False):
        variant_id_str = str(variant_id)
        try:
            variant = ProductVariant.objects.select_related('product').get(id=variant_id)
        except ProductVariant.DoesNotExist:
            logger.error(f"POS Cart: Variant {variant_id} not found.")
            return False

        stock = variant.stocks.filter(branch=self.branch).first()
        current = self.cart.get(variant_id_str, {}).get('quantity', 0)
        target = quantity if override_quantity else current + quantity
        if stock is None or target > stock.available_quantity:
            return False

        if variant_id_str not in self.cart:
            self.cart[variant_id_str] = {
                'type': 'variant',
                'quantity': 0,
                'price': str(variant.effective_price),
                'name': f"{variant.product.name} - {variant.option_summary}",
            }

        if override_quantity:
            self.cart[variant_id_str]['quantity'] = quantity
        else:
            self.cart[variant_id_str]['quantity'] += quantity

        if self.cart[variant_id_str]['quantity'] <= 0:
            self.remove_item(variant_id_str)
        else:
            self._save()
        return True

    def remove_item(self, variant_id):
        variant_id_str = str(variant_id)
        if variant_id_str in self.cart:
            del self.cart[variant_id_str]
            self._save()
            return True
        return False

    def get_cart_items_extended(self):
        variant_ids = [key for key in self.cart if not key.startswith('p:')]
        product_ids = [key[2:] for key in self.cart if key.startswith('p:')]
        variants = ProductVariant.objects.select_related(
            'product', 'product__category'
        ).prefetch_related('product__quantity_price_tiers').filter(id__in=variant_ids)
        products = Product.objects.select_related('category').prefetch_related(
            'quantity_price_tiers',
        ).filter(id__in=product_ids)

        variants = list(variants)
        products = list(products)
        product_quantities = {}
        for variant in variants:
            quantity = self.cart[str(variant.id)]['quantity']
            product_quantities[variant.product_id] = (
                product_quantities.get(variant.product_id, 0) + quantity
            )
        for product in products:
            quantity = self.cart[f'p:{product.pk}']['quantity']
            product_quantities[product.pk] = product_quantities.get(product.pk, 0) + quantity

        items = []
        for variant in variants:
            entry = self.cart[str(variant.id)]
            quantity = entry['quantity']
            quote = QuantityPricingService.quote(
                product=variant.product,
                regular_unit_price=variant.effective_price,
                current_unit_price=variant.effective_price,
                product_quantity=product_quantities[variant.product_id],
            )
            price = quote.unit_price
            stock = variant.stocks.filter(branch=self.branch).first()
            items.append({
                'variant': variant,
                'product': variant.product,
                'quantity': quantity,
                'price': price,
                'total_price': price * quantity,
                'name': entry.get('name', str(variant)),
                'available_quantity': stock.available_quantity if stock else 0,
                'wholesale_applied': quote.wholesale_applied,
                'quantity_discount_percentage': quote.discount_percentage,
                'quantity_tier_minimum': quote.tier_minimum,
            })
        for product in products:
            key = f'p:{product.pk}'
            entry = self.cart[key]
            quantity = entry['quantity']
            quote = QuantityPricingService.quote(
                product=product,
                regular_unit_price=product.price,
                current_unit_price=product.price,
                product_quantity=product_quantities[product.pk],
            )
            price = quote.unit_price
            stock = product.stocks.filter(branch=self.branch).first()
            items.append({
                'variant': None,
                'product': product,
                'quantity': quantity,
                'price': price,
                'total_price': price * quantity,
                'name': entry.get('name', product.name),
                'available_quantity': stock.available_quantity if stock else 0,
                'wholesale_applied': quote.wholesale_applied,
                'quantity_discount_percentage': quote.discount_percentage,
                'quantity_tier_minimum': quote.tier_minimum,
            })
        return items

    def get_total_financial_cost(self):
        return sum(item['total_price'] for item in self.get_cart_items_extended())

    def get_total_item_count(self):
        return sum(item['quantity'] for item in self.cart.values())

    def is_empty(self):
        return len(self.cart) == 0

    def _save(self):
        self.session.modified = True

    def save_cart_state(self):
        self._save()

    def flush_entire_cart(self):
        self.session[_POS_CART_KEY] = {}
        self._save()


class UnifiedSessionCartService:
    """Online storefront cart — browsing customer's shopping basket."""

    def __init__(self, request):
        self.request = request
        self.session = request.session
        cart = self.session.get(STOREFRONT_CART_KEY)
        if not cart:
            cart = {}
            if self._is_authenticated_customer():
                from orders.models import CustomerCart
                saved_carts = CustomerCart.objects.filter(
                    customer=request.user,
                    branch__is_active=True,
                )
                if self.selected_branch_id:
                    saved_carts = saved_carts.filter(branch_id=self.selected_branch_id)
                saved = saved_carts.order_by('-updated_at').first()
                if saved:
                    cart = deepcopy(saved.data)
                    self.session[STOREFRONT_CART_BRANCH_KEY] = saved.branch_id
                    self.session[STOREFRONT_SELECTED_BRANCH_KEY] = saved.branch_id
            self.session[STOREFRONT_CART_KEY] = cart
        self.cart = cart

    def _is_authenticated_customer(self):
        user = getattr(self.request, 'user', None)
        return bool(
            user and user.is_authenticated and user.is_active
            and getattr(user, 'role', None) == 'CUSTOMER'
        )

    @property
    def selected_branch_id(self):
        return self.session.get(STOREFRONT_SELECTED_BRANCH_KEY)

    @property
    def cart_branch_id(self):
        return self.session.get(STOREFRONT_CART_BRANCH_KEY)

    def _available_for_entry(self, branch_id, entry):
        from inventory.models import Stock
        if entry['type'] == 'variant':
            rows = Stock.objects.filter(branch_id=branch_id, variant_id=entry['variant_id'])
        else:
            rows = Stock.objects.filter(branch_id=branch_id, product_id=entry['product_id'])
        return _available_total(rows)

    def _allocate_branch(self, proposed_entry):
        """Choose one internal branch that can fulfil the complete proposed basket."""
        proposed_cart = deepcopy(self.cart)
        proposed_cart[proposed_entry['key']] = proposed_entry
        for branch in self._ordered_branches():
            if all(
                self._available_for_entry(branch.pk, entry) >= int(entry['quantity'])
                for entry in proposed_cart.values()
            ):
                return branch.pk
        return None

    def _ordered_branches(self):
        from branches.models import Branch
        branches = list(
            Branch.objects.filter(is_active=True)
            .order_by('-offers_customer_pickup', 'id')
        )
        if self.cart_branch_id:
            branches.sort(key=lambda branch: branch.pk != self.cart_branch_id)
        return branches

    def _best_partial_branch(self, proposed_entry):
        """Find a branch that fulfils existing lines and the largest safe new quantity."""
        other_entries = [
            entry for key, entry in self.cart.items()
            if key != proposed_entry['key']
        ]
        candidates = []
        for branch in self._ordered_branches():
            if not all(
                self._available_for_entry(branch.pk, entry) >= int(entry['quantity'])
                for entry in other_entries
            ):
                continue
            available = self._available_for_entry(branch.pk, proposed_entry)
            if available > 0:
                candidates.append((available, branch.pk))
        return max(candidates, key=lambda pair: pair[0], default=(0, None))

    def _bind_cart_to_branch(self, branch_id):
        if self.cart_branch_id != branch_id:
            previous_branch_id = self.cart_branch_id
            self.session[STOREFRONT_CART_BRANCH_KEY] = branch_id
            self.session[STOREFRONT_SELECTED_BRANCH_KEY] = branch_id
            if previous_branch_id and previous_branch_id != branch_id:
                self._persist_cart(previous_branch_id, data={})
            self._save()

    def merge_authenticated_cart(self, guest_cart, guest_branch_id):
        """Merge the pre-login guest cart with the saved cart for the same branch."""
        if not self._is_authenticated_customer() or not guest_cart or not guest_branch_id:
            return []
        from orders.models import CustomerCart
        saved = CustomerCart.objects.filter(
            customer=self.request.user,
            branch_id=guest_branch_id,
            branch__is_active=True,
        ).first()
        combined = deepcopy(saved.data) if saved else {}
        for key, entry in guest_cart.items():
            if key in combined:
                combined[key]['quantity'] = (
                    int(combined[key].get('quantity', 0)) + int(entry.get('quantity', 0))
                )
            else:
                combined[key] = deepcopy(entry)

        self.session[STOREFRONT_SELECTED_BRANCH_KEY] = guest_branch_id
        self.session[STOREFRONT_CART_BRANCH_KEY] = guest_branch_id
        self.session[STOREFRONT_CART_KEY] = {}
        self.cart = self.session[STOREFRONT_CART_KEY]
        warnings = []
        for entry in combined.values():
            quantity = max(int(entry.get('quantity', 0)), 0)
            if not quantity:
                continue
            if entry.get('type') == 'variant' and entry.get('variant_id'):
                result = self.add_variant(entry['variant_id'], quantity=quantity, override_quantity=True)
            elif entry.get('type') == 'product' and entry.get('product_id'):
                result = self.add_product(entry['product_id'], quantity=quantity, override_quantity=True)
            else:
                continue
            if result.get('warning') or result.get('error'):
                warnings.append(result.get('warning') or result.get('error'))
        self._save()
        return warnings

    # ------------------------------------------------------------------
    # VARIANT ITEMS
    # ------------------------------------------------------------------

    def add_variant(self, variant_id, quantity=1, override_quantity=False):
        key = f"v:{variant_id}"

        try:
            variant = ProductVariant.objects.select_related(
                'product', 'product__category'
            ).get(
                id=variant_id,
                product__status=Product.Status.ACTIVE,
                product__category__is_visible=True,
            )
        except ProductVariant.DoesNotExist:
            logger.warning(f"Storefront Cart: Variant {variant_id} not found.")
            return {'success': False, 'error': 'Product variant is not available.'}

        # ① Sum() aggregation -- database computes the total, not Python.
        current_quantity = int(self.cart.get(key, {}).get('quantity', 0))
        target_quantity = quantity if override_quantity else current_quantity + quantity
        proposed_entry = {
            'key': key,
            'type': 'variant',
            'variant_id': str(variant_id),
            'product_id': str(variant.product.id),
            'quantity': target_quantity,
        }
        branch_id = self._allocate_branch(proposed_entry)
        if not branch_id:
            partial_stock, branch_id = self._best_partial_branch(proposed_entry)
        else:
            partial_stock = None
        if not branch_id:
            any_stock = any(
                self._available_for_entry(branch.pk, proposed_entry) > 0
                for branch in self._ordered_branches()
            )
            return {
                'success': False,
                'error': (
                    'These items are not currently available together from one shop. Remove an item or contact us for help.'
                    if any_stock else f"'{variant.product.name} - {variant.option_summary}' is out of stock."
                ),
            }
        total_stock = self._available_for_entry(branch_id, proposed_entry)
        self._bind_cart_to_branch(branch_id)

        if key not in self.cart:
            self.cart[key] = {
                'type': 'variant',
                'variant_id': str(variant_id),
                'product_id': str(variant.product.id),
                'quantity': 0,
                'price': str(_resolve_display_price(variant)),
                'name': variant.product.name,
                'variant_name': variant.option_summary,
                'sku': '',  # ProductVariant has no sku field -- see prior note
            }
            

        if override_quantity:
            self.cart[key]['quantity'] = quantity
        else:
            self.cart[key]['quantity'] += quantity

        if self.cart[key]['quantity'] > total_stock:
            self.cart[key]['quantity'] = total_stock
            self._save()
            return {
                'success': True,
                'warning': f"Quantity capped at available stock ({total_stock} units).",
            }

        if self.cart[key]['quantity'] <= 0:
            self.remove_item(key)
        else:
            self._save()

        return {'success': True}

    # ------------------------------------------------------------------
    # SIMPLE PRODUCT ITEMS
    # ------------------------------------------------------------------

    def add_product(self, product_id, quantity=1, override_quantity=False):
        key = f"p:{product_id}"

        try:
            product = Product.objects.select_related('category').get(
                id=product_id,
                status=Product.Status.ACTIVE,
                category__is_visible=True,
            )
        except Product.DoesNotExist:
            logger.warning(f"Storefront Cart: Product {product_id} not found or inactive.")
            return {'success': False, 'error': 'Product is not available.'}

        if product.variants.exists():
            logger.warning(
                f"Storefront Cart: Product {product_id} has variants — "
                f"must be added via add_variant(), not add_product()."
            )
            return {
                'success': False,
                'error': 'This product has options (size/colour) — please select one.',
            }

        # ① Sum() aggregation -- database computes the total, not Python.
        current_quantity = int(self.cart.get(key, {}).get('quantity', 0))
        target_quantity = quantity if override_quantity else current_quantity + quantity
        proposed_entry = {
            'key': key,
            'type': 'product',
            'product_id': str(product_id),
            'quantity': target_quantity,
        }
        branch_id = self._allocate_branch(proposed_entry)
        if not branch_id:
            partial_stock, branch_id = self._best_partial_branch(proposed_entry)
        else:
            partial_stock = None
        if not branch_id:
            any_stock = any(
                self._available_for_entry(branch.pk, proposed_entry) > 0
                for branch in self._ordered_branches()
            )
            return {
                'success': False,
                'error': (
                    'These items are not currently available together from one shop. Remove an item or contact us for help.'
                    if any_stock else f"'{product.name}' is currently out of stock."
                ),
            }
        total_stock = self._available_for_entry(branch_id, proposed_entry)
        self._bind_cart_to_branch(branch_id)

        if key not in self.cart:
            self.cart[key] = {
                'type': 'product',
                'product_id': str(product_id),
                'quantity': 0,
                'price': str(product.price),
                'name': product.name,
                'sku': product.sku,
            }

        if override_quantity:
            self.cart[key]['quantity'] = quantity
        else:
            self.cart[key]['quantity'] += quantity

        if self.cart[key]['quantity'] > total_stock:
            self.cart[key]['quantity'] = total_stock
            self._save()
            return {
                'success': True,
                'warning': f"Quantity capped at available stock ({total_stock} units).",
            }

        if self.cart[key]['quantity'] <= 0:
            self.remove_item(key)
        else:
            self._save()

        return {'success': True}

    # ------------------------------------------------------------------
    # SHARED OPERATIONS
    # ------------------------------------------------------------------

    def remove_item(self, cart_key):
        if cart_key in self.cart:
            previous_branch_id = self.cart_branch_id
            del self.cart[cart_key]
            if not self.cart:
                self._persist_cart(previous_branch_id)
                self.session.pop(STOREFRONT_CART_BRANCH_KEY, None)
                self.session.modified = True
            else:
                self._save()
            return True
        return False

    def update_quantity(self, cart_key, new_quantity):
        if cart_key not in self.cart:
            return {'success': False, 'error': 'Item not in cart.'}

        if new_quantity <= 0:
            self.remove_item(cart_key)
            return {'success': True}

        item = self.cart[cart_key]
        if item['type'] == 'variant':
            return self.add_variant(item['variant_id'], quantity=new_quantity, override_quantity=True)
        else:
            return self.add_product(item['product_id'], quantity=new_quantity, override_quantity=True)

    def get_cart_items_extended(self):
        variant_entries = {k: v for k, v in self.cart.items() if v['type'] == 'variant'}
        product_entries = {k: v for k, v in self.cart.items() if v['type'] == 'product'}

        variant_ids = [v['variant_id'] for v in variant_entries.values()]
        active_tiers = QuantityPriceTier.objects.filter(is_active=True).order_by('minimum_quantity')
        variants_qs = ProductVariant.objects.select_related(
            'product', 'product__category'
        ).prefetch_related(
            Prefetch('product__quantity_price_tiers', queryset=active_tiers),
        ).filter(id__in=variant_ids)
        variants_map = {str(v.id): v for v in variants_qs}

        product_ids = [v['product_id'] for v in product_entries.values()]
        products_qs = Product.objects.select_related('category').prefetch_related(
            Prefetch('quantity_price_tiers', queryset=active_tiers),
        ).filter(id__in=product_ids)
        products_map = {str(p.id): p for p in products_qs}

        product_quantities = {}
        for entry in variant_entries.values():
            variant = variants_map.get(entry['variant_id'])
            if variant:
                product_quantities[variant.product_id] = (
                    product_quantities.get(variant.product_id, 0) + entry['quantity']
                )
        for entry in product_entries.values():
            product = products_map.get(entry['product_id'])
            if product:
                product_quantities[product.pk] = (
                    product_quantities.get(product.pk, 0) + entry['quantity']
                )

        items = []
        noticed_products = set()

        for key, entry in variant_entries.items():
            variant = variants_map.get(entry['variant_id'])
            if not variant:
                # ② Self-heal: remove the stale entry instead of leaving
                # it in the session forever.
                logger.warning(
                    f"Storefront Cart: Variant {entry['variant_id']} no longer "
                    f"exists — removing stale cart entry {key}."
                )
                self.remove_item(key)
                continue
            quantity = entry['quantity']
            quote = QuantityPricingService.quote(
                product=variant.product,
                regular_unit_price=variant.effective_price,
                current_unit_price=_resolve_display_price(variant),
                product_quantity=product_quantities[variant.product_id],
            )
            price = quote.unit_price
            items.append({
                'key': key,
                'type': 'variant',
                'name': f"{entry['name']} - {entry.get('variant_name', '')}",
                'sku': entry.get('sku', ''),
                'quantity': quantity,
                'price': price,
                'total_price': price * quantity,
                'variant': variant,
                'product': variant.product,
                'stored_price': Decimal(entry['price']),
                'regular_price': quote.regular_unit_price,
                'pricing_source': quote.source,
                'wholesale_applied': quote.wholesale_applied,
                'quantity_tier_minimum': quote.tier_minimum,
                'quantity_discount_percentage': quote.discount_percentage,
                'product_quantity': product_quantities[variant.product_id],
                'minimum_order_quantity': variant.product.minimum_order_quantity,
                'minimum_order_shortfall': max(
                    0,
                    variant.product.minimum_order_quantity - product_quantities[variant.product_id],
                ),
                'next_tier_minimum': quote.next_tier_minimum,
                'next_tier_shortfall': (
                    quote.next_tier_minimum - product_quantities[variant.product_id]
                    if quote.next_tier_minimum else 0
                ),
                'show_product_pricing_notice': variant.product_id not in noticed_products,
            })
            noticed_products.add(variant.product_id)

        for key, entry in product_entries.items():
            product = products_map.get(entry['product_id'])
            if not product:
                # ② Self-heal: same treatment for orphaned product entries.
                logger.warning(
                    f"Storefront Cart: Product {entry['product_id']} no longer "
                    f"exists — removing stale cart entry {key}."
                )
                self.remove_item(key)
                continue
            quantity = entry['quantity']
            quote = QuantityPricingService.quote(
                product=product,
                regular_unit_price=product.price,
                current_unit_price=product.price,
                product_quantity=product_quantities[product.pk],
            )
            price = quote.unit_price
            items.append({
                'key': key,
                'type': 'product',
                'name': entry['name'],
                'sku': entry.get('sku', ''),
                'quantity': quantity,
                'price': price,
                'total_price': price * quantity,
                'variant': None,
                'product': product,
                'stored_price': Decimal(entry['price']),
                'regular_price': quote.regular_unit_price,
                'pricing_source': quote.source,
                'wholesale_applied': quote.wholesale_applied,
                'quantity_tier_minimum': quote.tier_minimum,
                'quantity_discount_percentage': quote.discount_percentage,
                'product_quantity': product_quantities[product.pk],
                'minimum_order_quantity': product.minimum_order_quantity,
                'minimum_order_shortfall': max(
                    0, product.minimum_order_quantity - product_quantities[product.pk],
                ),
                'next_tier_minimum': quote.next_tier_minimum,
                'next_tier_shortfall': (
                    quote.next_tier_minimum - product_quantities[product.pk]
                    if quote.next_tier_minimum else 0
                ),
                'show_product_pricing_notice': product.pk not in noticed_products,
            })
            noticed_products.add(product.pk)

        return items

    def get_total_financial_cost(self):
        return sum(item['total_price'] for item in self.get_cart_items_extended())

    def get_total_item_count(self):
        return sum(item['quantity'] for item in self.cart.values())

    def is_empty(self):
        return len(self.cart) == 0

    def revalidate_stock(self, branch=None):
            """
            Hard stock + price re-validation at checkout start (spec §4).
            Stock issues are blocking ('issues'/'valid'). Price drift (a flash
            sale expired/started since add-to-cart) is auto-synced into the
            session cart and surfaced non-blockingly via 'price_changes' --
            additive key, existing 'valid'/'issues' consumers unaffected.
            """
            from inventory.models import Stock
            issues = []
            minimum_order_issues = []
            price_changes = []
            items = self.get_cart_items_extended()
            for item in items:
                if item['type'] == 'variant':
                    stock_rows = Stock.objects.filter(variant=item['variant'])
                    if branch is not None:
                        stock_rows = stock_rows.filter(branch=branch)
                    available = _available_total(stock_rows)
                    live_price = item['price']
                    if live_price != item['stored_price']:
                        self.cart[item['key']]['price'] = str(live_price)
                        self._save()
                        price_changes.append({
                            'key': item['key'],
                            'name': item['name'],
                            'old_price': str(item['stored_price']),
                            'new_price': str(live_price),
                        })
                else:
                    stock_rows = Stock.objects.filter(product=item['product'])
                    if branch is not None:
                        stock_rows = stock_rows.filter(branch=branch)
                    available = _available_total(stock_rows)
                    live_price = item['price']
                    if live_price != item['stored_price']:
                        self.cart[item['key']]['price'] = str(live_price)
                        self._save()
                        price_changes.append({
                            'key': item['key'],
                            'name': item['name'],
                            'old_price': str(item['stored_price']),
                            'new_price': str(live_price),
                        })
                if item['quantity'] > available:
                    issues.append({
                        'key': item['key'],
                        'name': item['name'],
                        'requested': item['quantity'],
                        'available': available,
                    })
                if item['show_product_pricing_notice'] and item['minimum_order_shortfall']:
                    minimum_order_issues.append({
                        'product_id': item['product'].pk,
                        'name': item['product'].name,
                        'required': item['minimum_order_quantity'],
                        'in_cart': item['product_quantity'],
                        'shortfall': item['minimum_order_shortfall'],
                    })
            return {
                'valid': len(issues) == 0 and len(minimum_order_issues) == 0,
                'issues': issues,
                'minimum_order_issues': minimum_order_issues,
                'price_changes': price_changes,
            }
        
    def _persist_cart(self, branch_id=None, data=None):
        if not self._is_authenticated_customer():
            return
        branch_id = branch_id or self.cart_branch_id
        if not branch_id:
            return
        from orders.models import CustomerCart
        cart_data = self.cart if data is None else data
        if cart_data:
            CustomerCart.objects.update_or_create(
                customer=self.request.user,
                branch_id=branch_id,
                defaults={'data': deepcopy(cart_data)},
            )
        else:
            CustomerCart.objects.filter(
                customer=self.request.user,
                branch_id=branch_id,
            ).delete()

    def _save(self):
        self.session.modified = True
        self._persist_cart()

    def flush_entire_cart(self):
        previous_branch_id = self.cart_branch_id
        self.session[STOREFRONT_CART_KEY] = {}
        self.cart = self.session[STOREFRONT_CART_KEY]
        self._persist_cart(previous_branch_id)
        self.session.pop(STOREFRONT_CART_BRANCH_KEY, None)
        self.session.modified = True
