# Manager operations guide

Managers are accountable for their own branch; super admins must deliberately select a branch before branch mutation.

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

## Reporting and follow-up

Use `/management/reports/` for the authorized branch/date range. Review sales, payment split, stock movements, transfers, discounts, voids, manual confirmations, failed payments, variances, delivery disputes, returns and promotion usage. Scheduled reports require an explicit recipient/configuration; no invented fallback address exists.

Escalate immediately: payment evidence mismatch, repeated callback, stock reversal failure, cross-branch exposure, audit-log concern, delivery dispute, material shift variance, repeated notification failure or suspected account compromise.
