# Phase 14 traceability

| Requirement | Evidence | Status |
|---|---|---|
| Model, service, permission, API and view tests | Django application test modules and full-suite command | Complete locally; final count recorded in verification |
| Checkout and payment regression coverage | `apps/orders/tests/test_checkout_api.py`, payment tests | Complete with mocked providers |
| Inventory concurrency and idempotency | inventory/payment service tests | Complete locally; PostgreSQL load proof pending staging |
| Fulfilment distinction | required checkout radio cards with no default, summary method, fulfilment-workspace badges and tests | Complete and verified |
| Live delivery price | checkout preview API plus rendered browser journey | Complete and verified |
| Coupon validity feedback | preview response contract, API tests and rendered browser journey | Complete and verified |
| Responsive critical journey | 390 x 844 and default desktop browser runs | Complete and verified for checkout changes |
| Cart icon and logo-derived favicon | base/navbar templates, page test and browser inspection | Complete and verified |
| Accessibility basics | semantic labels, live status regions and keyboard-addressable controls | Implemented; formal staging audit pending |
| Load, backup/restore and provider sandbox tests | Phase 13 staging/runbooks | Blocked on external infrastructure/credentials |
| Client acceptance | manual UAT guide and results template | Pending client execution |
