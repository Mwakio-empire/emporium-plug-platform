# Phase 10 business definitions

## Revenue

Recognized revenue is `Order.total_payable` when the order first reaches one of:

- `COMPLETED` for walk-in sales;
- `DELIVERED` or `CUSTOMER_CONFIRMED` for delivery;
- `COLLECTED` for pickup.

The first matching status-history timestamp is the recognition date. A legacy order without matching history falls back to its creation timestamp. Pending, processing, cancelled, voided, disputed and returned orders are excluded.

This is gross recognized order value, not accounting net revenue. Discounts and delivery fees are shown separately. Returns and refund obligations are reported separately because Phase 9 does not perform an automated, reconciled refund.

## Scope and time

- Branch managers are always restricted to their assigned branch, even if a different branch parameter is supplied.
- Super admins may select one branch or all branches.
- Calendar boundaries use the configured `Africa/Nairobi` timezone.
- Custom ranges are inclusive by date and limited to 366 days.

## Slow/dead stock

For the selected report period, a stock line is slow/dead when it has available stock but no recognized product sales in that period. It is an operational signal, not an accounting write-off.

## Scheduled delivery

Daily reports cover yesterday. Weekly reports cover the previous Monday through Sunday. Monthly reports cover the previous calendar month. Every schedule has an explicit recipient and optional branch scope. A delivery period is unique per schedule to prevent ordinary duplicate sends.
