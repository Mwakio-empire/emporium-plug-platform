# Phase 15 verification record

Date: 2026-07-26

## Documentation checks

- All 28 required document categories are mapped in the Phase 15 index.
- All project-local Markdown links across 109 repository documents resolve.
- Phase 15 files contain no known mojibake markers, placeholder claims or embedded credentials.
- Guides reference implemented routes/workflows and distinguish local verification from external certification.
- Known limitations, deferred features, client decisions and release gates are explicit.
- Current API, release, UAT, changelog and traceability documents agree that public launch checkout creates S18-pickup orders only; town parcels use the non-order-creating WhatsApp handoff.
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
