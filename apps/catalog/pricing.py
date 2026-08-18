from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


MONEY = Decimal('0.01')


@dataclass(frozen=True)
class QuantityPriceQuote:
    regular_unit_price: Decimal
    unit_price: Decimal
    source: str = 'REGULAR'
    tier_minimum: int | None = None
    discount_percentage: Decimal = Decimal('0.00')
    next_tier_minimum: int | None = None

    @property
    def wholesale_applied(self):
        return self.source == 'WHOLESALE'


class QuantityPricingService:
    """Resolve one non-stacking unit price for a product quantity."""

    @staticmethod
    def quote(*, product, regular_unit_price, current_unit_price, product_quantity):
        regular = Decimal(str(regular_unit_price)).quantize(MONEY, rounding=ROUND_HALF_UP)
        current = Decimal(str(current_unit_price)).quantize(MONEY, rounding=ROUND_HALF_UP)
        tiers = [tier for tier in product.quantity_price_tiers.all() if tier.is_active]
        eligible = [tier for tier in tiers if tier.minimum_quantity <= product_quantity]
        next_tier = next(
            (tier for tier in tiers if tier.minimum_quantity > product_quantity),
            None,
        )

        if not eligible:
            return QuantityPriceQuote(
                regular_unit_price=regular,
                unit_price=current,
                source='FLASH_SALE' if current < regular else 'REGULAR',
                next_tier_minimum=getattr(next_tier, 'minimum_quantity', None),
            )

        tier = max(eligible, key=lambda candidate: candidate.minimum_quantity)
        discount = Decimal(str(tier.discount_percentage))
        wholesale_price = (
            regular * (Decimal('100.00') - discount) / Decimal('100.00')
        ).quantize(MONEY, rounding=ROUND_HALF_UP)

        if current < wholesale_price:
            return QuantityPriceQuote(
                regular_unit_price=regular,
                unit_price=current,
                source='FLASH_SALE' if current < regular else 'REGULAR',
                next_tier_minimum=getattr(next_tier, 'minimum_quantity', None),
            )
        return QuantityPriceQuote(
            regular_unit_price=regular,
            unit_price=wholesale_price,
            source='WHOLESALE',
            tier_minimum=tier.minimum_quantity,
            discount_percentage=discount,
            next_tier_minimum=getattr(next_tier, 'minimum_quantity', None),
        )
