# Phase 4 - Complete Checkout

## Status

Complete and verified. The client confirmed on 2026-07-22 that cash payment is permitted for both delivery and branch pickup, with the complete payable amount displayed and explicit customer agreement required before order creation.

## Implemented checkout

- Authenticated and guest delivery/pickup checkout from the session cart.
- Mandatory phone, optional name and email, with phone normalization and email validation.
- Active branch, branch-owned delivery zone, and active/non-expired pickup-slot validation.
- Read-only final-total preview with live stock and price revalidation, delivery fee and coupon discount.
- Explicit confirmation after the reviewed total.
- API-level confirmation enforcement: bypassing the page cannot create an order without explicit agreement.
- Cash payment for delivery and pickup. Delivery cash totals include the delivery fee; pickup cash totals do not. Valid discounts remain reflected in the final payable amount.
- UUID idempotency keys, payload fingerprints, owner/session binding and safe replay without duplicate orders or stock reservations.
- Guest orders use the inactive, non-loggable system automation account for required audit actors; human identity is never fabricated.
- Signed guest access tokens expire after seven days. Tokens are placed in the URL fragment, then sent to the status API in a request header so they are not stored in normal URL logs.
- Guest and authenticated tracking page, M-Pesa pending polling, failure/fallback messaging, and an optional account-registration link.
- Coupon redemption locks the coupon row before checking and incrementing its global limit.
- Pickup slots can have an explicit start/end window protected by a database constraint.
- Checkout JavaScript is a local static asset, uses text-only DOM updates for untrusted values, and exposes useful live status messages.
- `LOCAL_CACHE_ONLY=True` permits an isolated development server without Redis. It is rejected outside development/test; production still requires Redis.

The Phase 1.5 inventory decision is retained: checkout reserves stock immediately to prevent overselling; M-Pesa failure/expiry releases it exactly once, while successful payment consumes it. This differs from the business-context sentence saying reservation occurs at payment confirmation, but it is the safer previously documented concurrency policy.

## Verification

- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `python -m compileall -q apps config`: passed.
- Focused checkout suite: 59 tests passed.
- Full suite: 268 tests passed; one PostgreSQL-only row-lock test skipped on SQLite.
- Browser: guest delivery quote, pickup switch, explicit confirmation, COD order, protected tracking and optional registration link passed.
- Browser at 390 x 844: no horizontal overflow after correction.
- Browser console: no errors or warnings.
- JavaScript syntax: both checkout assets passed `node --check`.
- Pinned frontend build: passed.
- `npm audit --audit-level=high`: zero vulnerabilities.
- `python -m pip check`: no broken requirements.

`pip-audit` is not installed in the project environment, so no new dependency-vulnerability claim is made for this phase.

## Accepted cash-payment decision

Cash payment is allowed for both delivery and branch pickup. The customer must see the complete final payable amount and explicitly agree to place the order. See [ADR-001](adr-001-cash-fulfilment-scope.md).

## Phase boundary

Daraja callback certification, amount/reference matching, polling reconciliation and production payment activation remain Phase 5. Browser acceptance did not call a live or sandbox Daraja endpoint.
