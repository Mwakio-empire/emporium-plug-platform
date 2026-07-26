# Change log

## Unreleased — client MVP candidate

### Added

- Multi-branch storefront/cart, explicit delivery/S18 pickup checkout and signed guest tracking.
- Cash/COD and M-Pesa subsystem with exact-amount/idempotent callback handling and reconciliation.
- Shift-bound POS, receipts, manager discounts, reversal voids and variance review.
- OTC intake, inventory states, transfers/partial receipt, counts and low-stock alerts.
- Packing, rider delivery, pickup codes/reminders/expiry and disputes.
- Promotions, verified reviews, eligible non-clothing returns and operational reports.
- Durable notifications, security/privacy artifacts, production blueprints/runbooks and testing/UAT pack.
- Phase 15 engineering and operations handover set.

### Changed

- Storefront redesigned for mobile/desktop with client colors, cart icon and exact logo-derived trolley favicon.
- Internal branch choice removed from customers; the system allocates one shop for the basket.
- Checkout requires explicit delivery or S18-pickup choice; neither is preselected.
- Delivery fee updates live and coupon feedback states valid/invalid clearly.
- Saturday counts as a pickup working day; Sunday does not.

### Security/correctness

- Central order transitions, locked stock mutations, audit history and idempotent reversals.
- Staff OTP, manager password re-authentication, throttling and branch/object authorization.
- Callback inbox, duplicate/unknown handling, exact settlement and release-once semantics.
- Pillow upgraded from 12.2.0 to 12.3.0 to resolve the vulnerabilities reported by the dependency audit.
- Established an isolated project Git repository on `main`; local secrets, databases, uploads, generated output and dependency directories are excluded from version control.

### Not externally verified

- Production infrastructure is unprovisioned.
- Provider certification, PostgreSQL restore/load/security evidence and client UAT remain gates.
- Automated refunds, offline POS, image search, hardware certification and routing remain deferred.
