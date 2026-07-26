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
