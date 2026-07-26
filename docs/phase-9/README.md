# Phase 9: promotions, reviews and returns

Status: implemented and verified. The client approved a seven-calendar-day request window for explicitly eligible non-clothing goods on 22 July 2026.

## Promotions

- Fixed and percentage coupons with active windows, minimum spend, global usage limit and authenticated/guest per-customer limit.
- Optional branch scope; an empty branch list means all branches.
- Atomic row locking and an immutable `CouponRedemption` record prevent duplicate counting for one order.
- Guest limits use a keyed digest of the checkout phone identity; the promotion ledger does not add another plaintext phone field.
- One coupon per order. Manual manager discounts cannot stack with coupons.
- A coupon may apply to a subtotal whose item prices already include a valid flash sale. Multiple coupons and bundle deals are unsupported.
- Flash sales reject invalid windows, prices at/above normal price, and overlapping active campaigns.
- Configuration changes through Django administration and every successful redemption create audit records.

Product/category coupon scope and bundle deals are deferred because the client has not required them. They must not be inferred from branch scope.

## Reviews

- Only confirmed purchasers may submit a review.
- One current review per customer/product is enforced in the database.
- The MVP policy does not allow customer amendments. A second submission is rejected.
- Reviews remain private until a manager records approval/rejection, reason and timestamp.
- Moderation is audited and cannot silently be repeated.
- Public output uses the customer's first name only, or “Verified customer”; surname, phone and email are not exposed.
- Submission rate limiting provides a basic abuse control.
- Approved current reviews feed the product average rating and structured data.

## Returns

- Authenticated customers can request an item-level quantity from their own completed order.
- Products use an explicit customer-return policy: `SEVEN_DAY` or `SUPPORT_ONLY`. New and unclassified products default to support-only so clothing cannot accidentally enter self-service returns.
- Catalog staff must opt eligible non-clothing goods into `SEVEN_DAY`; clothing/fashion goods remain support-only.
- The order item is locked while cumulative pending/approved quantity is checked, preventing over-return races.
- Managers are branch-scoped; super admins may see all branches.
- Approval requires condition assessment, stock disposition and a reason.
- Sellable stock returns to on-hand inventory. Damaged or uncertain stock enters the unavailable/quarantine bucket.
- Every inventory movement and return decision is auditable and idempotent.
- Refund status is recorded as no-refund-required, pending manual, completed manual or declined.
- The system does not initiate automated refunds. `PENDING_MANUAL` is an operational reconciliation obligation, not proof that money was sent.

## Approved client decision

`RETURN_REQUEST_WINDOW_DAYS` defaults to `7`. This is a request window, not automatic approval or refund. Wrong or defective-item concerns for support-only goods must still be handled by customer support. The client should have the public wording reviewed by qualified Kenyan legal/compliance guidance before launch.

See [traceability](traceability.md), [business rules](business-rules.md), [browser acceptance](browser-acceptance.md), [verification](verification.md), and [defect register](defect-register.md).
