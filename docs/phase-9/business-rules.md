# Phase 9 business rules

## Stacking

An order may use one coupon. A manual manager discount and coupon cannot coexist. Flash-sale prices are item prices, so a valid coupon may discount a subtotal that already contains flash-sale-priced items. This policy is centralized in `PromotionService`.

## Review policy

One verified-purchase review is allowed per customer and product. Customers cannot amend it in the MVP. A manager may approve or reject once with a mandatory reason. Rejected reviews remain retained for accountability but never appear publicly.

## Return and stock policy

Customer self-service is available for seven calendar days after delivery/collection only when the purchased product is explicitly classified `SEVEN_DAY`. Clothing/fashion and every new or unclassified product use `SUPPORT_ONLY`. Eligibility is stored on the product; category names are never guessed in application code. Support-only does not mean staff should ignore a wrong or defective item.

Pending and approved quantities count against a purchased line's remaining returnable quantity; rejected quantities do not. Approval requires a physical condition and one disposition:

- `SELLABLE`: add to on-hand stock;
- `DAMAGED`: add to the unavailable/damaged bucket;
- `QUARANTINED`: add to the unavailable bucket pending a later assessment.

No approved quantity is simultaneously sellable and quarantined. Replaying a decision cannot move stock twice.

## Refund boundary

Refund statuses are accounting/operations records only. There is no Daraja reversal or bank refund integration in Phase 9. Staff must not mark a manual refund complete without independently verified payment evidence and reconciliation.
