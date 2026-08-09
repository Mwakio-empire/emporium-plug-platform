# Manager operations guide

## Configure colour images

1. Open **System data administration → Product option values**.
2. Open the colour value, for example `Everyday Heavyweight Hoodie — Colour: Grey`.
3. Under **Product option value images**, upload the Grey product photographs.
4. Describe each photograph accurately in **Alt text**, including the product and
   visible colour. Use sort order `0` for the primary image, then `1`, `2` and so on.
5. Save and check the public product page at desktop and mobile widths. Selecting
   Grey should replace the main image and thumbnail strip for every Grey size.

Upload colour media once per colour, not once per size. An image saved on one
exact product variant overrides the primary colour image for that SKU; use that
only when the SKU genuinely looks different. When neither exists, the storefront
uses the general product gallery. Colour galleries are deliberately unavailable
for Size, Capacity and other non-colour options.

## Configure wholesale quantity pricing

1. Open **System data administration → Products** and select the product.
2. Set **Minimum order quantity** only when the client requires a product-level minimum. Leave it at `1` otherwise.
3. Under **Quantity price tiers**, add each approved threshold and percentage, for example a threshold of `12` with an approved percentage. Do not enter unapproved commercial values.
4. Use a unique threshold for each tier and keep only current tiers active.
5. Save, then verify the product page and cart. Sizes, colours and other variants of the same product count together.

The lowest eligible automatic price wins when a flash sale is active. Quantity pricing cannot be combined with a coupon or a POS manager discount. Completed order lines retain the regular price and tier evidence for audit and reporting.

For coupons, the default is no stacking with discounted or flash-sale products. Enable **Allow discounted items** only for a specifically approved campaign; the coupon will then apply to the already-reduced subtotal. Wholesale/quantity pricing still never stacks. One coupon is allowed per order.

Managers are accountable for their own branch; super admins must deliberately select a branch before branch mutation.

## Back-office navigation

The back office is intentionally one staff experience with two clearly separated surfaces:

- **Operations** (`/management/dashboard/`) is the default working area. Use its role-scoped navigation for orders, fulfilment, POS, inventory, returns, reviews, reports and notification follow-up.
- **System data** (`/admin/`) is the Django administration surface. It is available only to superusers for controlled configuration and investigation. Order records there are read-only; operational state changes must use the validated Operations workflows so permissions, stock effects and audit records are preserved.

Question-mark icons beside less familiar navigation items show concise help on hover and keyboard focus. On phones, use the menu button to open the same role-scoped navigation. Staff should never share accounts or ask another person to perform an action merely to bypass a missing permission.

## Daily opening

- Confirm web, worker and Beat health, branch staff access, delivery/pickup configuration and unresolved overnight alerts.
- Review low stock, in-transit transfers, unpaid/expired orders, pickup deadlines, failed notifications, payment reconciliation and prior shift variances.
- Confirm S18 is the only ordinary customer-pickup branch unless the client formally changes policy.

## Approvals

- Discount: inspect items/total, enter your own password and mandatory reason.
- Void: verify original sale, shift state and physical stock; approve a reversal, never deletion.
- Manual payment: use provider/statement evidence, exact amount/unique receipt and a reason.
- Return: verify order ownership, eligible quantity/window, item condition and disposition. `PENDING_MANUAL` refund is an obligation, not proof of payment.
- Transfer: request/approve/dispatch/receive according to physical custody; never mark received before counting.

## Fulfilment

Use `/api/logistics/workspace/` for packing and pickup/delivery operations. Delivery cards are labelled `DELIVERY`; S18 collection cards are labelled `S18 PICKUP`. Complete every packing line, assign only an available same-branch rider and do not claim dispatch until rider pickup. Pickup confirmation requires the customer code and is attempt-limited.

## Town-parcel quote desk

Open **Operations → Delivery quotes**. Work oldest requests first. Staff may see and update only their branch; super admins must select the intended branch. Start review, verify the current operator/route, then publish the exact collection point, fee and expected arrival. Do not copy terms from an old quote without reconfirming them. Publication creates a 24-hour customer acceptance window and queues the ready notification after commit. A quote is not an order, reservation or payment. If it expires or is declined, do not create a hidden order; ask the customer to submit a current request.

## Reporting and follow-up

Use `/management/reports/` for the authorized branch/date range. Review sales, payment split, stock movements, transfers, discounts, voids, manual confirmations, failed payments, variances, delivery disputes, returns and promotion usage. Scheduled reports require an explicit recipient/configuration; no invented fallback address exists.

Escalate immediately: payment evidence mismatch, repeated callback, stock reversal failure, cross-branch exposure, audit-log concern, delivery dispute, material shift variance, repeated notification failure or suspected account compromise.
