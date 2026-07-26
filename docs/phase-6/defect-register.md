# Phase 6 defect register

| ID | Severity | Defect / business impact | Resolution status |
|---|---|---|---|
| POS-001 | Critical | No bounded active shift; repeated close could reconcile the same sales. | Resolved with `POSShift`, one-open-shift constraint and order association. |
| POS-002 | High | Simple products disappeared during cart expansion. | Resolved and regression tested. |
| POS-003 | High | Lookup was not branch-stock scoped. | Resolved with branch stock filtering and availability display. |
| POS-004 | High | Simple product search displayed a stale variant price. | Resolved by rendering the product price. |
| POS-005 | High | Reconciliation used a calendar day instead of one shift. | Resolved with locked shift aggregation. |
| POS-006 | High | Exact matches entered manager review. | Resolved with material-review state and threshold. |
| POS-007 | High | Reconciliation verification lacked reason, timestamp and audit. | Resolved with mandatory evidence and immutable operational audit. |
| POS-008 | Medium | Discount lacked a reason and could stack with a coupon. | Resolved; reason required and stacking refused pending Phase 9. |
| POS-009 | Medium | Receipt omitted payment, tender and change. | Resolved for PDF and SMS. |
| POS-010 | Medium | No customer-facing amount display. | Resolved with a standalone authenticated display. |
| POS-011 | Medium | Internal engine/gateway language appeared in cashier UI. | Resolved with ordinary retail language. |
| POS-012 | Critical | POS template contained duplicate closing template tags and failed to render. | Found by browser QA, resolved and rendered successfully. |
| POS-013 | High | Successful checkout left the cart and submit control visible briefly. | Found by browser QA; successful HTMX response now replaces the full tray. |
| POS-014 | Medium | Customer display inherited staff navigation and identity. | Found by browser QA; display is now a standalone minimal page. |
| POS-015 | Medium | Navbar linked to stale `/core/pos-workspace/`. | Found by browser QA; now uses the named `/pos-desk/` route. |

No open Critical or High Phase 6 defect remains in the locally tested scope.
