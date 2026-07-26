# Phase 4 Defect Register

## Resolved P0

- Guest checkout and guest audit representation.
- Duplicate order submission through checkout idempotency.
- Guest order tracking and cross-order access protection.
- Authenticated tracking lookup previously failed to filter by the supplied order number and could return a different owned order.
- Simple-product price changes were not revalidated at checkout.

## Resolved P1

- Pickup expiry representation and validation.
- Final-total preview.
- Coupon global-limit race protection.
- Guest email persistence.
- Inline checkout JavaScript.
- Incomplete payment progress and tracking link.
- Review-total button incorrectly required final confirmation before showing the total.
- Redis-backed API throttling caused local checkout HTTP 500 responses when Redis was unavailable; explicit development-only local-cache mode added.
- Five-pixel mobile horizontal overflow caused by duplicate page padding.

## Resolved decision blocker

- **Cash scope:** client approved cash payment for both delivery and branch pickup on 2026-07-22. Delivery includes its fee; pickup has no delivery fee. API-level explicit confirmation is mandatory.

## Deferred to Phase 5

- Real Daraja sandbox certification and callback reconciliation.
- Production payment activation.
- Bounded STK query polling at the financial service layer.

## Environment limitation

- `pip-audit` is unavailable in the virtual environment.
- One PostgreSQL-only row-lock test is skipped by the local SQLite test database and must run in a PostgreSQL staging/CI job.
