# Change log

## 2026-08-12 - Verified-review preview integrity

- Extended the non-production review seeder with controlled completed-order
  evidence so the verified-purchase badge can be inspected end to end.
- Demo feedback remains visibly labelled `Sample review`; it cannot be mistaken
  for genuine customer testimony, and the command remains blocked in production.

## 2026-08-11 - Simpler destination entry and stock privacy

- Removed the global shopping-location prompt so customers can browse without
  supplying a destination.
- Replaced the dependent county/town checkout selectors with typed county, town
  and collection-area fields. County names are still validated against the
  active Kenyan county reference; staff still verifies the route, operator,
  collection point and fee before payment.
- Removed the remaining browser suggestion list from the county field, so both
  county and town are ordinary text inputs with no selection step.
- Replaced public exact inventory quantities with `In stock`, `Low stock - order
  soon` and `Out of stock` states. Exact quantities remain available to internal
  inventory and ordering logic.
- Aligned catalogue cards with product-detail availability: products with active
  variants now count only active-variant stock, ignoring inactive variants and
  obsolete direct-product stock. Versioned product-page JavaScript prevents an
  older cached option selector from showing contradictory availability.

## 2026-08-09 - Storefront variant selector polish

- Replaced the plain product-option controls with compact size chips and true
  colour swatches while retaining accessible labels and keyboard operation.
- Variant selection now gives a clear selected state and updates the variant ID,
  price, regular sale price, stock message, SKU, image and cart availability.
- Rendered arbitrary validated colour values without weakening the storefront's
  Content Security Policy.
- Browser-verified the size-and-colour flow on desktop and mobile without
  horizontal overflow or console errors.
- Added reusable ordered galleries to colour option values, with a super-admin
  upload workflow and validation that rejects media on non-colour options.
- Selecting a colour now replaces the main image and thumbnails for every size;
  an exact SKU image overrides the colour gallery and the general product gallery
  remains the final fallback.

## 2026-08-02 - Persistent shopping location selector

- Added a familiar County → City/Area selector to the storefront and product pages.
- The validated selection is stored in the shopper session and prefills the town-parcel quote fields at checkout.
- Added an explicit unlisted-area fallback and retained staff verification of the operator, collection point and transport price.
- Selecting a shopping location does not create an order, reserve stock or promise a transport route.
- Superseded on 2026-08-11 by checkout-only typed destination entry after client
  review found the browsing prompt and dependent selectors unnecessarily complex.

## 2026-08-01

- Added guest and signed-in customer SMS restock requests for exact simple products or variants, with Kenyan phone normalization, duplicate prevention, abuse throttling, 90-day expiry and opaque cancellation links.
- Added a five-minute restock sweep that queues one durable notification only after sellable stock returns; subscriptions are closed after queuing and never reserve stock.
- Added customer-facing sold-out UI that follows variant selection, clearly states the non-reservation rule and exposes alert management in the originating browser session.
- Registered operational administration, notification event metadata, schedule documentation and automated coverage for signup, variants, cancellation, expiry, rate limits and post-commit dispatch.

## 2026-07-31

- Hardened and polished customer authentication with a 15-character passphrase
  minimum, password-manager metadata, accessible labels, visible password
  controls, clear passphrase guidance and preserved post-registration redirects.
- Added an authenticated, rate-limited and audited customer password-change flow
  that keeps the current browser session while invalidating other sessions and
  API tokens.
- Browser-verified phone/email sign-in, registration controls, password visibility
  and the complete password-change journey against PostgreSQL without contacting
  external notification providers.
- Replaced text password-visibility links with accessible eye icons positioned
  inside password fields, retaining masking state labels and live passphrase guidance.
- Recovered the local PostgreSQL environment after Windows dynamically reserved
  host port `5432`: retained the existing PostgreSQL volume, preserved the old
  stopped container definition for rollback and rebound the active service to
  loopback port `55432`.
- Reverified PostgreSQL readiness and the exact migrated counts for users,
  products, variants, inventory, orders and migrations; Redis remained healthy.
- Added a safe local startup helper that starts both containers, checks service
  readiness, configures Django without displaying the local database password and
  serves the site on port `8002`.

## 2026-07-30

- Migrated the verified local SQLite business dataset to an isolated PostgreSQL
  17 database through a rehearsal-first fixture process; preserved the SQLite and
  older sandbox sources without merging records.
- Corrected PostgreSQL outer-join row-lock incompatibilities across transfers,
  returns, cancellation, reports, parcel fulfilment and low-stock scanning.
- Passed the PostgreSQL concurrency test, 130 focused regressions and all 608
  automated tests; verified Django cache and Celery broker access through Redis.
- Created and successfully restored a PostgreSQL custom-format archive, with
  matching user, catalogue, variant, stock, order and migration counts.
- Browser-verified the PostgreSQL storefront, guest wishlist persistence, variant
  cart, S18-pickup checkout, protected admin redirect and 390 px mobile layout.
- Replaced one-pair catalogue variants with structured, ordered product options and true multi-option SKU combinations while preserving legacy records.
- Added colour swatches, combination-aware size/colour/capacity selectors, per-combination price/stock/SKU updates and full variant labels in cart/POS/API output.
- Added administrator option/value editing and an idempotent missing-combination generator with duplicate-combination protection.
- Added an idempotent four-product visual catalogue fixture with four original Cloudinary images, 27 variants and audited S18 stock.
- Published `0797 727 486` as the first customer-support telephone while retaining `0116 153 335` as the approved WhatsApp-order number.
- Verified the exact M + Orange cart journey, four image cards and 390 px mobile rendering; full suite now passes 602 tests with one SQLite row-lock skip.

## 2026-07-29

- Unified the custom operations workspaces and Django administration through a shared staff entry path and two-way navigation.
- Replaced the cluttered analytics landing page with a role- and branch-scoped operations overview using real actionable counts.
- Added contextual help, responsive staff navigation and a simplified, clearly labelled System data administration surface.
- Routed direct Django admin authentication through the staff login and privileged OTP flow; non-staff accounts are denied.
- Made order records in System data read-only so fulfilment and payment transitions remain in audited workflows.

## Unreleased — client MVP candidate

### Added

- Added all 47 Kenyan counties, a maintained KNBS 2019 urban-centre baseline, a rate-limited county town endpoint, dependent checkout selectors and an explicit unlisted-town fallback. County/town relationships are revalidated on the server and selecting a town does not promise a route or price.
- Added an atomic, idempotent `import_kenya_towns` command plus searchable, filtered town administration with deletion disabled. Imports require an explicit revision, reject unknown counties/duplicates before writing, preserve and report matching KNBS/manual records as skipped, and can deactivate only missing imported records from the supplied revision. Successful admin/import changes invalidate affected town caches after commit without treating cache failure as a database rollback.
- Added a protected town-parcel quote workflow: pickup remains default; customers request county/town/area pricing without creating an order; branch staff publishes operator, collection point, fee and ETA; the customer gets a 24-hour acceptance window and current-total confirmation before one prepaid M-Pesa order reserves stock.
- Added Monday-Saturday 8:00 AM-6:00 PM quote-desk timing, a 30-working-minute response target, configurable closure dates, overdue WhatsApp escalation and quote-ready SMS/email queueing after commit.
- Added controlled coupon stacking with an explicit per-coupon discounted-item override, separate product/coupon savings and wholesale non-stacking.
- Added configurable product minimum quantities and percentage quantity-price tiers shared across sizes, colours and other variants, with locked order-line evidence and consistent storefront/POS calculations.
- Added clear mobile-safe notifications and active-restock-alert state so the subscription form is replaced after a successful request.
- Multi-branch storefront/cart, S18-pickup checkout, protected town-parcel quote access and signed guest order tracking.
- Added a protected ten-minute customer cancellation grace period for unpaid online orders, with confirmation, release-once inventory handling, audit history, throttling and late-M-Pesa reconciliation safeguards.
- Cash/COD and M-Pesa subsystem with exact-amount/idempotent callback handling and reconciliation.
- Shift-bound POS, receipts, manager discounts, reversal voids and variance review.
- OTC intake, inventory states, transfers/partial receipt, counts and low-stock alerts.
- Packing, rider delivery, pickup codes/reminders/expiry and disputes.
- Promotions, verified reviews, eligible non-clothing returns and operational reports.
- Durable notifications, security/privacy artifacts, production blueprints/runbooks and testing/UAT pack.
- Phase 15 engineering and operations handover set.

### Changed

- Customer-facing cart, checkout and notification errors now explain what happened and the next safe action; technical checkout identifiers are no longer exposed in normal guidance.
- Quantity prices do not stack with coupons, manager discounts or flash-sale discounts; the lowest eligible automatic unit price wins.
- Storefront redesigned for mobile/desktop with client colors, cart icon and exact logo-derived trolley favicon.
- Internal branch choice removed from customers; the system allocates one shop for the basket.
- Launch checkout selects S18 pickup; “Send to my town” starts a non-order quote request. WhatsApp is delayed-response/support fallback. Only explicit quote acceptance creates the prepaid parcel order.
- Pickup fee remains zero, the final payable total updates correctly, and coupon feedback states valid/invalid clearly.
- Saturday counts as a pickup working day; Sunday does not.

### Security/correctness

- Central order transitions, locked stock mutations, audit history and idempotent reversals.
- Staff OTP, manager password re-authentication, throttling and branch/object authorization.
- Callback inbox, duplicate/unknown handling, exact settlement and release-once semantics.
- Pillow upgraded from 12.2.0 to 12.3.0 to resolve the vulnerabilities reported by the dependency audit.
- Established an isolated project Git repository on `main`; local secrets, databases, uploads, generated output and dependency directories are excluded from version control.
- Scheduled-report email now has validated opt-in Brevo SMTP settings, records configuration/render/provider failures, and prevents blind duplicate sends with a `PROCESSING` delivery state.
- PostgreSQL logical backups now use streaming checksums and required TLS mode in deployed environments; a separate verification command rejects unencrypted, corrupted or unreadable uploaded archives before restore testing.
- Added a no-store operational health probe and one-minute Beat-to-worker heartbeat, plus explicit Sentry environment/release and Celery error integration controls.
- Added a bounded GET-only capacity probe, pinned Python audit tools, CI dependency/static scans and an independent penetration-test rules-of-engagement runbook.
- Removed disposable staging media, required Cloudinary in every deployed environment, added safe single-secret deployment wiring and verified a synthetic upload/delivery/delete round trip.
- Isolated automated tests from developer and production Cloudinary accounts by
  using local test storage and a synthetic URL-generation identity.
- Added checksum-pinned local validation of both Render Blueprints against Render's official JSON Schema without exporting repository configuration.
- Hardened deployed privacy and notification fail-fast gates while preserving suppressed synthetic-data staging operation.

### Not externally verified

- Production infrastructure is unprovisioned.
- Provider certification, PostgreSQL restore/load/security evidence and client UAT remain gates.
- Automated refunds, offline POS, image search, hardware certification and routing remain deferred.
