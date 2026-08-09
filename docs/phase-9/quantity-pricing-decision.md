# Quantity pricing decision

Date: 2026-08-01
Status: implemented locally; commercial values await client approval

## Decision

- A product may have an optional minimum order quantity. The default is one, so existing products are unchanged.
- A product may have any number of active percentage discount tiers, each beginning at a unique minimum quantity.
- Quantities of the same product count together across sizes, colours and other variants.
- The application compares the eligible quantity price with any active flash-sale price and uses the lower unit price. Discounts do not stack.
- Coupons and POS manager discounts cannot be combined with an applied quantity price.
- Each order line stores the regular price, charged price, pricing source, qualifying threshold and percentage. This preserves audit and reporting evidence after catalog prices change.
- The same calculator is used by storefront checkout and walk-in POS.

## Why this approach

Percentage tiers remain fair when variants have different regular prices. Product-level counting matches wholesale buying behaviour while retaining variant-level inventory. A single calculator prevents the cart, checkout, order record and POS from showing different totals.

## Not configured by engineering

No minimum quantities, tier thresholds or discount percentages have been invented or seeded. A manager must enter client-approved commercial values in product administration before customers see or receive a quantity price.

## Deferred commercial features

Gift cards and store credit are excluded from the launch scope. Referrals are also deferred; if later approved, rewards become eligible only after a completed paid purchase that has not been refunded, with fraud and reversal controls.
