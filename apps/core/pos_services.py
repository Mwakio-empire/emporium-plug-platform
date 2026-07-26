import logging
from decimal import Decimal
from django.conf import settings
from catalog.models import ProductVariant
from inventory.models import Stock

logger = logging.getLogger(__name__)

class BranchIsolatedPOSCartService:
    """
    Enterprise transaction state tracker managing point-of-sale items inside staff sessions.
    Strictly isolated by branch locations to enforce accurate stock balance verifications.
    """
    def __init__(self, request, branch):
        self.session = request.session
        self.branch = branch
        # Use a distinct key descriptor suffix to isolate terminal sales from standard consumer storefronts
        self.cart_key = f"{settings.SESSION_COOKIE_NAME}_pos_cart_{self.branch.id}"
        
        cart = self.session.get(self.cart_key)
        if not cart:
            cart = self.session[self.cart_key] = {}
        self.cart = cart

    def add_or_update_variant(self, variant_id, quantity=1, override_quantity=False):
        """
        Validates real-time branch stock rules before writing active tracking state modifications.
        """
        variant_id_str = str(variant_id)
        try:
            variant = ProductVariant.objects.select_related('product').get(id=variant_id)
            # Fetch branch stock record mapped out in Phase 5
            stock_record = Stock.objects.get(branch=self.branch, variant=variant)
        except (ProductVariant.DoesNotExist, Stock.DoesNotExist):
            logger.error(f"POS Stock Isolation Violation: Target variant ID {variant_id} unmapped at branch {self.branch.id}.")
            return False, "Target item variant is not stocked at this branch location."

        current_qtyInCart = self.cart.get(variant_id_str, {}).get('quantity', 0)
        target_qty = quantity if override_quantity else (current_qtyInCart + quantity)

        if target_qty > stock_record.available_quantity:
            return False, f"Insufficient stock. Available branch balance: {stock_record.available_quantity} units."

        if target_qty <= 0:
            self.remove_variant(variant_id)
            return True, "Item variant purged from terminal instance ledger view."

        if variant_id_str not in self.cart:
            self.cart[variant_id_str] = {
                'quantity': 0,
                'price': str(variant.product.price),
                'discount': '0.00'
            }

        self.cart[variant_id_str]['quantity'] = target_qty
        self.save_state()
        return True, "Terminal selection matrix state modified successfully."

    def apply_item_discount(self, variant_id, discount_amount):
        """
        Applies flat currency reductions onto specific variant components inside the current loop structure.
        """
        variant_id_str = str(variant_id)
        if variant_id_str in self.cart:
            self.cart[variant_id_str]['discount'] = str(Decimal(discount_amount))
            self.save_state()
            return True
        return False

    def remove_variant(self, variant_id):
        """
        Purges an active variant listing completely from the current terminal cache sequence.
        """
        variant_id_str = str(variant_id)
        if variant_id_str in self.cart:
            del self.cart[variant_id_str]
            self.save_state()
            return True
        return False

    def get_ledger_items(self):
        """
        Resolves full variant entries for the current branch session in a single batch query, avoiding N+1 overhead.
        """
        variant_ids = self.cart.keys()
        variants = ProductVariant.objects.select_related('product', 'product__category').filter(id__in=variant_ids)
        
        compiled_items = []
        for variant in variants:
            entry = self.cart[str(variant.id)]
            qty = entry['quantity']
            base_price = Decimal(entry['price'])
            item_discount = Decimal(entry['discount'])
            total_cost = (base_price * qty) - item_discount

            compiled_items.append({
                'variant': variant,
                'quantity': qty,
                'price': base_price,
                'discount': item_discount,
                'total_cost': max(total_cost, Decimal('0.00'))
            })
        return compiled_items

    def get_grand_total_cost(self):
        """
        Computes financial liabilities after incorporating any managerial item reductions.
        """
        return sum(item['total_cost'] for item in self.get_ledger_items())

    def save_state(self):
        self.session.modified = True

    def clear_terminal_cache(self):
        self.session[self.cart_key] = {}
        self.save_state()
