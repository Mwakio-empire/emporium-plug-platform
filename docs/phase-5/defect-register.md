# Phase 5 defect register

All PAY-001 through PAY-010 and CASH-001 are resolved and covered by automated tests. External sandbox certification and PostgreSQL staging verification remain manual release gates rather than code defects.

| ID | Severity | Defect and impact | Resolution |
|---|---|---|---|
| PAY-001 | Critical — resolved | STK query result `0` settled an order without amount or receipt. | Query confirmation is evidence-only until callback or audited reconciliation. |
| PAY-002 | Critical — resolved | Customer fallback reference overwrote provider identifiers and was treated as a receipt. | Submitted references are stored separately and are never proof. |
| PAY-003 | Critical — resolved | Success callback with missing amount could settle. | Exact amount and unique provider receipt are mandatory. |
| PAY-004 | High — resolved | Callback merchant request ID was not matched. | Both provider request identifiers must match. |
| PAY-005 | High — resolved | Provider request preceded the local payment record and retries could send duplicate prompts. | An `INITIATING` record is created first and active attempts are reused. |
| PAY-006 | High — resolved | Full callback metadata retained unnecessary phone data. | Only minimized, sanitized evidence is retained. |
| PAY-007 | High — resolved | Pending-order cancellation existed but was absent from Celery Beat. | Five-minute cleanup schedule added. |
| CASH-001 | High — resolved | POS cash lacked tender/change evidence and insufficient-cash rejection. | Tender and change persist; insufficient tender rolls back atomically. |
| PAY-008 | Medium — resolved | Provider exception details could reach users. | Stable public errors and exception-type-only logging added. |
| PAY-009 | Medium — resolved | Whole-KES conversion silently rounded fractional totals. | Unsupported fractional STK totals are rejected. |
| PAY-010 | Medium — resolved | Unknown/malformed callbacks were acknowledged without durable operational state. | A deduplicated callback inbox stores sanitized evidence, review state, delivery count and audited resolution. Database unavailability returns HTTP 503. |
