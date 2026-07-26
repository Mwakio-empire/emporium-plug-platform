# Phase 8 browser acceptance

Executed 22 July 2026 against an isolated SQLite browser-test database with local-only task configuration and synthetic phone numbers. No live customer, payment or messaging provider was used.

| Journey | Result |
|---|---|
| Storefront search/cart pattern, original logo asset, orange/blue theme and footer | Pass |
| WhatsApp CTA appears only when a test configuration number is present | Pass |
| Manager staff login with mandatory 2FA | Pass |
| Start pickup packing, check every line and seal parcel | Pass |
| Mark packed pickup ready at S18 and display two-working-day deadline | Pass |
| Confirm S18 collection with pickup code | Pass |
| Pack online delivery and assign an available same-branch rider | Pass |
| Assignment remains `RIDER_ASSIGNED` and visibly waits for physical rider pickup | Pass |
| Customer sees protected order status and chronological progress timeline | Pass |
| Customer-facing navigation avoids internal scope/engine terminology | Pass |

The test database, synthetic session and local server are removed after acceptance. Rider GPS/status updates and SMS confirmation/dispute are covered by automated API tests; real-device/provider testing remains part of client UAT and sandbox certification.
