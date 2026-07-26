# Phase 6 traceability

| Requirement | Final state | Verification evidence |
|---|---|---|
| Product/SKU search | Complete and verified | Branch stock filtering, availability display and browser search. |
| Variant selection | Complete and verified | Variant cart and POS regression tests. |
| Cart quantity/running total | Complete and verified | Mixed simple/variant cart tests and browser KES 150 total. |
| Customer phone | Complete and verified | Service normalization and checkout tests. |
| Cash payment | Complete and verified locally | Tender/change persisted; browser sale and receipt tests. |
| Paybill payment | Implemented and locally verified | Manager password, reason and audit tests; provider certification remains Phase 5. |
| Manager discount | Complete and verified locally | Manager re-authentication, mandatory reason and audit tests. |
| Receipt | Complete and verified locally | Authorized PDF response and SMS content tests; browser link present. |
| Stock deduction | Complete and verified locally | Atomic service, stock audit and POS tests. |
| Shift association | Complete and verified | `Order.pos_shift`, open-shift enforcement and reconciliation tests. |
| Sale audit trail | Complete and verified locally | Cashier, branch, shift and privileged-action evidence persisted. |
| Void reversal | Complete and verified for open shifts | Manager re-authentication, immutable order and stock-once tests. |
| End-of-shift reconciliation | Complete and verified | One locked shift, opening float and payment split tests. |
| Variance escalation | Complete and verified | KES 50 threshold and manager notification tests. |
| Manager discrepancy verification | Complete and verified | Actor, timestamp, reason and operational audit tests. |
| Customer amount display | Complete and browser verified | Standalone authenticated display contains items/totals and no operator navigation. |
| Duplicate sale UI protection | Complete and browser verified | Successful response retargets the entire tray and removes the submit button. |

"Verified locally" does not mean hardware, Daraja production or client UAT certification.
