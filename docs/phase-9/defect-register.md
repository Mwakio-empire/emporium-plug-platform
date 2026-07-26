# Phase 9 defect register

| Severity | Finding | Resolution/state |
|---|---|---|
| P0 | Coupon use had no redemption ledger and could be counted twice by a repeated service call | One-order redemption ledger and idempotent return added |
| P1 | Per-customer and branch coupon limits were absent | Added authenticated/guest keyed limit and optional branch scope |
| P1 | Promotion stacking behavior conflicted across modules | Central policy: one coupon and no manual-discount stacking |
| P1 | Duplicate review prevention was view-only and race-prone | Database uniqueness plus atomic service handling |
| P1 | Review moderation had no actor/reason/timestamp audit | Added manager workflow and immutable audit event |
| P1 | Return quantity aggregation was not serialized | Order item locking added before cumulative validation |
| P1 | Return approval lacked condition, disposition, refund and decision audit | Added required operational fields and manager workflow |
| P1 | Approved returns were always treated as damaged | Manager must select sellable, damaged or quarantine disposition |
| P1 | Return window was not approved | Resolved: client approved seven calendar days for explicitly eligible non-clothing goods |
| P1 | Category-name matching could misclassify clothing | Avoided: explicit per-product policy with safe support-only default |
