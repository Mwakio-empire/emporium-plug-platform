# Phase 14 verification record

Date: 2026-07-26  
Environment: local development/test configuration, isolated Django test databases and mocked external providers.

This is a dated Phase 14 snapshot. Its delivery-selector browser evidence was superseded by the later client-approved S18-pickup/WhatsApp launch policy; it remains here to preserve honest test history. Current release evidence is recorded in [Phase 15 verification](../phase-15/verification.md).

## Automated checks

| Check | Result |
|---|---|
| Checkout/page regression after explicit fulfilment-choice change | 38 passed |
| JavaScript syntax check | Passed |
| Django system check | Passed |
| Migration drift check | Passed; no changes detected |
| Python compile check | Passed |
| Frontend production build | Passed; only the non-blocking Browserslist data-age warning was emitted |
| Full Django suite | 504 run: 503 passed and 1 PostgreSQL row-lock test skipped because local SQLite does not provide `select_for_update` |

Expected 4xx and simulated provider-failure log entries in negative tests are test evidence, not failures.

## Browser journey

The local storefront was exercised through the rendered UI, not inferred from templates:

1. Added the KES 100 smoke product and observed the icon quantity change from 0 to 1.
2. Opened guest checkout and confirmed neither delivery nor pickup was preselected; the summary displayed `Not selected` and both detail sections remained hidden.
3. Explicitly selected delivery, then selected the KES 75 smoke delivery zone; the summary changed from KES 100 to KES 175 without reload.
4. Applied `INVALID14`; the page displayed `This coupon is inactive, expired, or invalid.`
5. Applied a temporary KES 10 QA coupon; the page confirmed validity and changed the total to KES 165.
6. Switched to S18 pickup, selected a temporary future pickup slot, and confirmed zero delivery fee and a KES 90 total after discount.
7. Switched fulfilment again and confirmed stale coupon feedback and discount were cleared until revalidation.
8. Repeated the delivery pricing and valid-coupon controls at 390 x 844. No page-level horizontal overflow was detected.
9. Verified the cart is an accessible icon with quantity badge and the favicon uses the approved logo's trolley emblem.
10. Browser error/warning logs were empty on desktop and mobile.

The temporary QA coupon and pickup slot were removed after testing. No order or payment was submitted and no external provider was contacted.

## External gates

| Gate | Status |
|---|---|
| Daraja sandbox certification | Pending credentials and controlled sandbox execution |
| PostgreSQL concurrency/load suite on production-sized staging | Pending staging provision |
| Backup restore and measured RPO/RTO | Pending managed PostgreSQL staging backup |
| Provider notification sandbox | Pending approved provider credentials |
| External security/accessibility review | Pending staging URL and reviewer |
| Client UAT | Pending client execution using the results template |
