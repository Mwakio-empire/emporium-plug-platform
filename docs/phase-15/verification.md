# Phase 15 verification record

## Production re-audit update — 2026-08-16

- Authoritative business context and active runtime paths were rechecked rather
  than relying on integration file presence.
- Django checks, migration drift, Python compilation, dependency consistency,
  Python/production-JavaScript vulnerability audits and the frontend build pass.
- Complete SQLite regression: **718 passed, 1 expected PostgreSQL row-lock
  feature skip, 0 failed**.
- Repeatable PostgreSQL release verification applies migrations, checks drift,
  compiles and runs the complete suite without printing protected local
  credentials: **718 passed, 0 skipped, 0 failed**.
- Focused PostgreSQL final-unit locking, payment-idempotency/polling and
  stock-restoration regression: **31 passed, 0 skipped, 0 failed**.
- The ordinary local `.env` remains SQLite for lightweight development; release
  evidence must use `start_local_postgres.ps1 -VerifyRelease` on the committed SHA.
- Deployed Django default media storage now uses Cloudinary; tests remain
  synthetic/local. Focused deployed-setting suite: **15 passed**.
- Bandit's medium/high CI command passes after reviewing two findings: ordinary
  option-validation text was rewritten to avoid an SQL false positive, and the
  fixed Africa's Talking HTTPS URL has a narrowly documented `B310` exception.
- GitHub Actions now provisions PostgreSQL 17 and Redis 7 instead of using
  SQLite for the exact release-commit test job. A green pushed run is still
  required before Phase 0 passes.
- Demo catalogue and simulated review commands both fail closed in production;
  the catalogue production guard has dedicated regression coverage.
- The re-audit identified unscheduled logical backups, optional production
  Sentry, disabled report email, unprovisioned Render resources and uncompleted
  provider/UAT/security gates. They remain blockers; no readiness label was
  inflated to hide them.

## Pre-production hardening update — 2026-08-09

- Inventory transfer receipt locks source and destination balances in stable
  branch-ID order to prevent opposite-direction PostgreSQL deadlocks.
- SMS and transactional-email attempts use a durable delivery lease. Concurrent
  tasks do not contact the provider twice; an expired lease with unknown provider
  outcome enters manual follow-up instead of being blindly resent.
- Production refuses to start with M-Pesa sandbox mode, disabled transactional
  email, incomplete Daraja credentials or a disabled off-site backup job.
- Checkout, tracking and authentication utility pages emit
  `noindex,nofollow`; public catalogue and policy content remains crawlable.
- `manage.py check`, migration drift and Python compilation passed. Migration
  `notifications.0004` is applied locally.
- Complete SQLite regression: **710 run, 709 passed, 1 expected SQLite
  row-lock feature skip, 0 failed**.
- Complete PostgreSQL regression: **710 passed, 0 skipped, 0 failed**. It exposed
  and drove correction of nullable-outer-join row locks in restock alerts and
  delivery-quote acceptance, plus a migration test that relied on flushed county
  seed data. The focused modules and final global PostgreSQL run all pass.
- In-app browser QA passed on the default desktop viewport and 390×844 mobile:
  storefront rendering, product search, checkout privacy/layout and the sign-in
  password visibility control. No browser console warnings/errors were recorded.
- `pip-audit` and `npm audit --omit=dev` reported no known vulnerabilities;
  Bandit reported no high-severity findings. Python dependencies remain exactly
  version-pinned but are not yet hash-locked.
- Production-style `check --deploy` passes with only the deliberately deferred
  HSTS include-subdomains/preload warnings; those controls remain off until every
  real subdomain is verified as HTTPS-only.
- The exact release revision still requires PostgreSQL, rendered browser,
  provider, recovery, load, external security and client-UAT evidence.

Date: 2026-07-26

## Documentation checks

- All 28 required document categories are mapped in the Phase 15 index.
- All project-local Markdown links across 109 repository documents resolve.
- Phase 15 files contain no known mojibake markers, placeholder claims or embedded credentials.
- Guides reference implemented routes/workflows and distinguish local verification from external certification.
- Known limitations, deferred features, client decisions and release gates are explicit.
- This dated 26 July statement has been superseded by the 1 August update below: S18 pickup remains default, while town parcels now use a non-order quote request with WhatsApp as delayed-response/support fallback.
- Older delivery-selector records are retained as dated historical evidence and explicitly point readers to the superseding launch policy.
- All 48 concrete paths sampled from the API reference resolve through Django's active URL configuration.

## Repository checks

| Check | Result |
|---|---|
| Repository isolation | Passed; project resolves to its own Git work tree on `main` instead of the unrelated parent repository |
| Repository hygiene | Passed; runtime secrets/data, dependency directories and generated output are excluded from the baseline |
| Django system check | Passed; no issues |
| Migration drift | Passed; no changes detected |
| Python compilation | Passed |
| Dependency consistency | Passed; no broken requirements |
| Python vulnerability audit | Passed; `pip-audit` found no known vulnerabilities after Pillow 12.3.0 upgrade |
| Production JavaScript vulnerability audit | Passed; `npm audit --omit=dev` found 0 vulnerabilities |
| Frontend build | Passed; Browserslist data-age warning only |
| Scheduled-report email | 18 focused tests passed; configuration/render/provider failures and duplicate suppression verified without external delivery |
| Full automated suite | 519 run: 518 passed, 1 expected SQLite skip for PostgreSQL row locking |

Expected external gates are recorded in the release checklist; they are not silently converted into local passes.

## Delivery quote and controlled-stacking update — 2026-08-01

- S18 pickup remains selected by default. “Send to my town” creates a protected quote request without creating an order, initiating payment, reserving stock or redeeming a coupon.
- Quote timing implements Monday-Saturday 8:00 AM-6:00 PM Africa/Nairobi, a 30-working-minute response target, configured closure dates and a 24-hour acceptance window.
- Commercial quote publication is branch-scoped and restricted at both the view and service layers to branch managers/super admins. The workspace uses the unified Operations navigation.
- Acceptance rehydrates server-owned product identities, rechecks current stock/pricing/coupon rules, requires the current total to be explicitly reconfirmed, and creates one prepaid M-Pesa parcel order/reservation under row locks.
- Coupon rules are controlled: one coupon; quantity pricing never stacks; discounted/flash items reject coupons unless the coupon explicitly permits them; savings and transport fee are displayed separately.
- Focused checkout/marketing/logistics/notification suite: **151 passed**.
- Final complete suite: **654 passed, 1 expected `select_for_update` feature skip, 0 failed**.
- `manage.py check`, migration drift, Python compilation and both checkout JavaScript syntax checks passed. Migrations `marketing.0004`, `orders.0014` and `orders.0015` are applied locally.
- Local HTTP smoke checks returned 200 for the storefront, checkout and delivery-quote JavaScript asset. The in-app browser policy blocked automated control of the localhost page, so final desktop/mobile rendered UAT remains an explicit manual gate rather than a claimed pass.

## Item 10 update — 2026-07-28

- Bounded capacity probe and adversarial JSON-LD escaping tests: 5 passed.
- Full suite: 550 passed, 1 expected SQLite/PostgreSQL row-lock skip, 0 failed.
- Bandit 1.9.4: zero medium/high findings after a reviewed, regression-backed
  suppression for the required escaped JSON-LD safe output.
- Local GET probe: 100/100 HTTP 200, zero failures, concurrency 10 and
  1034.62 ms p95 on the Windows Django development server. This validates the
  tool only and is not production capacity evidence.
- Current Python dependency audit: `pip-audit 2.10.1 -r requirements.txt`
  completed successfully and reported no known vulnerabilities. Corrupt local
  cache entries were ignored and did not prevent the advisory lookup from
  completing.
- Current production JavaScript dependency audit:
  `npm audit --omit=dev --audit-level=moderate` completed successfully and
  reported 0 vulnerabilities.
- These dependency and static-analysis checks are automated security controls;
  they are not evidence of an independent penetration test.

## Item 11 update — 2026-07-28

- Deployed environments now fail closed unless Cloudinary is configured; the
  temporary staging filesystem exception was removed.
- Eighteen focused deployment-setting, Blueprint, image-validation and
  provider-cleanup tests passed.
- The configured client Cloudinary account passed a controlled synthetic
  write/delivery/delete round trip: HTTPS delivery returned 68 bytes from
  `res.cloudinary.com`, and the verification asset was deleted.
- The local database has one product, no product image and no gallery images,
  so no catalog-media migration is required.
- Persistence through an actual Render redeploy cannot be evidenced until the
  funded staging environment exists.
- Complete regression: 556 passed, 1 expected SQLite/PostgreSQL row-lock skip,
  0 failed.

## Item 12 update — 2026-07-28

- Both staging and production Blueprints pass Render's current official JSON
  Schema locally; CI downloads the public schema, verifies its pinned SHA-256,
  and validates the local files without uploading them.
- Render CLI v2.22.0 was downloaded from its official release and matched the
  publisher's SHA-256.
- The client explicitly authorized workspace-aware validation. Both files
  reached Render successfully and returned only `need_payment_info` for their
  five paid resources; no other provider validation error was reported and no
  resources were created.
- The temporary Render CLI authentication was logged out after validation and
  the verified temporary tooling was removed.

## Item 13 update — 2026-07-28

- Staging remains explicitly synthetic and non-delivering: an unapproved
  privacy notice and the console notification provider are permitted there.
- Production now rejects absent or invalid controller/privacy-contact data,
  an unapproved notice, console or unknown notification providers, incomplete
  Africa's Talking credentials and the Africa's Talking sandbox account.
- Thirty-five focused tests passed before the final email-format gate; all 9
  deployment-setting tests then passed.
- Complete regression: 562 passed, 1 expected SQLite/PostgreSQL row-lock skip,
  0 failed.

## Item 14 update — 2026-07-28

- The client-owned private GitHub remote and authenticated CLI access were
  verified without exposing the authentication token.
- GitHub Actions run `30362283936` failed at the Django test step with two
  `CloudinaryField` URL-generation errors because CI had no Cloudinary cloud
  name. Dependency installation, compilation, Django checks and migration
  drift had passed before that failure.
- Automated tests now force local media storage and a synthetic Cloudinary
  identity. The two formerly failing tests and the new isolation regression
  test pass.
- Complete local regression: **563 passed, 1 expected SQLite/PostgreSQL
  row-lock skip, 0 failed**. Django checks, migration drift, compilation,
  Bandit medium/high analysis, `collectstatic` and the frontend build passed.
- A green remote CI result requires committing and pushing this reviewed batch;
  it is not claimed from local execution alone.

## Item 15 update — 2026-07-28

- All 28 required handover categories remain mapped to their current source of
  truth. Production/provider claims remain clearly separated from local
  evidence.
- All project-local links across 115 Markdown files resolve after the final
  documentation updates.
- The funding reminder remains a mandatory release-checklist gate: add a valid
  client-owned Render payment method, review the current estimate and approve
  resource creation before deployment.
- Final documentation/link and dependency-audit results are recorded only after
  their commands complete; no unavailable external result is treated as a pass.
