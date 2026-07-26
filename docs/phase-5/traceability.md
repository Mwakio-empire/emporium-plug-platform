# Phase 5 requirements traceability

| Requirement | Current state | Evidence / action |
|---|---|---|
| Environment-specific credentials | Implemented but externally unverified | Only `sandbox` and `production` are accepted; credentials remain environment variables. Sandbox certification is pending. |
| STK initiation | Complete and verified locally | Local lifecycle is created first; repeated active requests reuse it; failures are safely recorded. |
| Public callback routing | Complete and verified | `/payments/mpesa/callback/` is wired and exercised by tests. |
| Durable callback operations queue | Complete and verified locally | Every callback is recorded before parsing; malformed, unknown and conflicting events require audited resolution. |
| Strict parsing and safe logging | Complete and verified locally | Stable logs omit phone/receipt; only sanitized callback evidence is retained. |
| Payment record before/during initiation | Complete and verified | `INITIATING` row is committed before the provider request. |
| Unique request/receipt identifiers | Complete and verified | Provider IDs, receipts, and submitted references have database uniqueness controls. |
| Idempotent callback | Complete and verified locally | Row locking plus stock movement uniqueness prevents duplicate settlement. |
| Exact amount/reference validation | Complete and verified locally | Merchant/checkout IDs, amount, and receipt are mandatory for automatic settlement. |
| Partial/overpayment handling | Complete and verified locally | Both enter `RECONCILIATION_REQUIRED`; fulfilment remains pending. |
| Poll missing callback | Complete and verified locally | Query success records evidence only and awaits callback/manual reconciliation. |
| Manual fallback | Complete and verified locally | Separate submitted reference plus branch-scoped manager re-authentication and risk audit. |
| Walk-in C2B automatic matching | Deferred by accepted business decision | Amount-and-time matching was rejected as unsafe. ADR-001 requires a C2B-enabled client shortcode, unique order reference, exact amount, unique provider transaction ID and provider certification before implementation. |
| Failure releases inventory once | Complete and verified | Atomic row locking and stock audit tests cover duplicate failure callbacks. |
| Paid order enters processing | Complete and verified | Callback moves PENDING to PROCESSING, not COMPLETED. |
| Cash amount/change/cashier/branch | Complete and verified locally | Tender and change are persisted; insufficient cash rolls back atomically. |
| Shift and reconciliation | Partially implemented | Existing day-based reconciliation includes cash orders; formal active shift is Phase 6. |
| Production certification | Deferred with justification | Requires Daraja sandbox and written production authorization. |
