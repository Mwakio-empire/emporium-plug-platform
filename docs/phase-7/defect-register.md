# Phase 7 defect register

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| INV-001 | Critical | Supplier intake could be represented as an unrestricted positive adjustment at any shop. | Added hub-only supplier intake with delivery identity and line audits. |
| INV-002 | High | Transfer skipped an approval state. | Added source approval before dispatch. |
| INV-003 | High | Existing transfer was source-only and could not model a Gaborone shop requesting OTC stock. | Requester may belong to either participating branch; source approval remains mandatory. |
| INV-004 | High | Transfer supported only one all-or-nothing receipt. | Added partial receipts and remaining in-transit custody. |
| INV-005 | High | No cancellation service despite a declared status. | Added reasoned cancellation before dispatch. |
| INV-006 | High | Manual stock operations lacked centralized branch authorization and retry identity. | Added authorized, referenced, idempotent adjustment service/API. |
| INV-007 | High | No executable stock-count workflow. | Added open/count/complete/cancel workflow and stale-snapshot protection. |
| INV-008 | Medium | Low-stock sweep aggregated all branches and notified repeatedly every hour. | Scheduler now uses per-branch durable edge-trigger alerts. |
| INV-009 | Medium | Branch model could not distinguish a supplier receiving hub. | Added explicit configurable capability. |

No open Critical or High defect remains in the implemented Phase 7 backend scope.
