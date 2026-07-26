# Phase 6 - POS and staff accountability

Status: **implemented and locally verified** on 2026-07-22.

## Delivered scope

- Branch-scoped product and SKU search with available quantities.
- Simple-product and variant carts with server-side stock enforcement.
- One active shift per cashier, opening cash and shift-bound sales.
- Cash tender and change, plus existing manager-verified Paybill handling.
- Manager password re-authentication and a mandatory reason for discounts.
- Printable PDF and SMS receipts containing payment, tender and change details.
- Immutable void reversals with manager authorization and stock restoration once.
- Shift reconciliation based on opening cash plus completed cash sales.
- Material variance escalation and reasoned manager verification audit.
- Customer display containing only the current items, quantities and total.
- Immediate removal of checkout controls after a successful sale.

## Safety decisions

- Manual discounts cannot stack with coupons until the Phase 9 promotion policy is approved.
- A sale on a closed shift cannot be voided through the ordinary void endpoint. It must use the future audited return/correction workflow so a closed drawer is not silently changed.
- Exact and immaterial shift variances do not enter the manager review queue. A variance greater than KES 50 does.
- Offline/PWA sales remain deferred because conflict resolution, duplicate-sale protection and local data security require a separate design.

## Verification status

- Focused Phase 6 suite: 62 passed.
- Full suite: 295 passed, 1 skipped.
- Django checks: passed with no issues.
- Migration drift check: no changes detected.
- Python compilation: passed.
- Browser journey: staff password plus OTP login, shift open, branch search, cart, customer display, KES 150 cash sale with KES 200 tender and KES 50 change, receipt link, duplicate-submit control removal, and balanced shift close all passed.

The skipped test is the existing PostgreSQL row-lock/concurrency test. It remains a staging gate and is not treated as passed on SQLite.

## Remaining external/manual gates

- Hardware barcode scanners and receipt printers have not been certified.
- Any fiscal/tax-device requirement needs a client and Kenyan tax adviser decision.
- Paybill provider operations still depend on the Phase 5 Daraja/manual certification gates.
- Client UAT must confirm cashier ergonomics, opening-float policy and receipt layout.
