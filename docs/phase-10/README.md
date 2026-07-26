# Phase 10: reports and client operations

Status: complete and verified on 22 July 2026. PostgreSQL load testing and client UAT remain production gates rather than Phase 10 code failures.

## Delivered scope

- One branch-authorized operations workspace and JSON API.
- Daily, weekly, monthly and custom ranges up to 366 days in `Africa/Nairobi`.
- Recognized sales, branch comparison, walk-in staff, payment method and sales-channel splits.
- Product velocity, current inventory, slow/dead stock, stock movements and transfers.
- Voids, discounts, manual payment confirmations, failed/reconciliation payments and shift variances.
- Rider assignments, completed deliveries, average delivery duration and disputes.
- Returns, pending manual refunds and promotion usage.
- CSV export for reconciliation and a visually verified A4 PDF management summary.
- Explicit scheduled-report configurations with recipient, frequency, branch scope and retained delivery outcome.

The previous unconditional midnight email and invented fallback recipient were removed. Only active, explicitly configured schedules are dispatched.

## Important boundaries

- Report revenue is gross recognized order value. Returns and manual refund obligations are shown separately and are not silently netted.
- No report marks a manual refund as paid.
- CSV exports intentionally exclude customer phone, email and payment-provider payloads.
- Failed scheduled email is recorded for manual follow-up and is not blindly retried. Durable notification retries and provider-level delivery state belong to Phase 11.
- PostgreSQL performance/load verification and client UAT remain production gates.

See [business definitions](business-definitions.md), [traceability](traceability.md), [defect register](defect-register.md), and [verification](verification.md).
