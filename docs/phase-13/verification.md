# Phase 13 verification

## Commands

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py check --deploy
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe -m compileall -q apps config
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe manage.py collectstatic --noinput
npm.cmd run build
```

## Evidence recorded during implementation

- Focused backup suite after archive-verification hardening: **7 passed, 0 failed**.
- Uploaded archives now fail closed when encryption metadata is absent, the
  SHA-256 differs or `pg_restore` cannot read the catalog. These are mocked
  local controls, not evidence of an actual S3 upload or database restore.
- Full regression on 2026-07-28 after Item 8 local hardening: **538 passed,
  1 expected SQLite/PostgreSQL row-lock skip, 0 failed**. Django checks,
  migration drift and Python compilation also passed.
- Item 9 monitoring regression: **16 focused tests passed**. The complete suite
  then passed **545 tests with 1 expected SQLite/PostgreSQL row-lock skip and
  0 failures**; Django checks, migration drift, compilation and diff checks
  passed.
- Item 10 local tool validation: 5 focused tests passed before the complete
  regression; Bandit 1.9.4 reported zero medium/high findings after reviewing
  and regression-testing the JSON-LD safe-output exception. A bounded local
  HTTP probe completed 100 requests at concurrency 10 with 100 HTTP 200
  responses, 0 failures and 1034.62 ms p95. This is tool validation, not hosted
  capacity evidence.
- Complete regression after Item 10 tooling: **550 passed, 1 expected
  SQLite/PostgreSQL row-lock skip, 0 failed**. Django checks, migration drift,
  Python compilation, dependency consistency, the frontend build and diff
  checks passed.
- Current Item 10 advisory checks on 2026-07-28 passed: `pip-audit 2.10.1`
  reported no known Python dependency vulnerabilities and
  `npm audit --omit=dev --audit-level=moderate` reported 0 production
  JavaScript vulnerabilities. These scans do not replace external penetration
  testing.
- Item 11 persistent-media checks on 2026-07-28: 18 focused settings, Blueprint,
  upload-validation and cleanup tests passed. A controlled live Cloudinary round trip
  uploaded a synthetic 1×1 PNG, delivered 68 bytes over HTTPS from
  `res.cloudinary.com`, and confirmed deletion. No catalog images required
  migration. Render redeploy persistence remains a funded-staging acceptance
  gate.
- Complete regression after Item 11: **556 passed, 1 expected
  SQLite/PostgreSQL row-lock skip, 0 failed**. Django checks, migration drift,
  Bandit medium/high analysis and diff checks passed.
- Item 12 local Blueprint validation on 2026-07-28: `render.staging.yaml` and
  `render.yaml` both passed Render's official JSON Schema with verified schema
  SHA-256 `665539cb0c191856ba38d292b985a963880bb69b030d666e5fe7788e78e7e696`.
  The client then explicitly authorized provider validation. Render CLI 2.22.0
  validated both files against Michael's workspace and returned only
  `need_payment_info` for web, worker, Beat, Key Value and PostgreSQL in each
  Blueprint. No resources were created. The temporary CLI token was logged out
  and the checksum-verified temporary executable/schema files were removed.
- Item 13 staging/production safety checks: 35 focused privacy, notification,
  Blueprint and settings tests passed, followed by 9 focused fail-closed
  deployment tests after contact-email validation was added. Production now
  rejects missing or invalid privacy approval, console/unknown providers,
  missing Africa's Talking credentials and sandbox credentials.
- Complete regression after Item 13: **562 passed, 1 expected
  SQLite/PostgreSQL row-lock skip, 0 failed**. Django checks, migration drift,
  Bandit medium/high analysis and diff checks passed.
- Static production build: 177 files copied and 511 post-processed after resolving the Cloudinary override conflict.
- CI media isolation: test settings now force local filesystem storage and a
  synthetic Cloudinary identity. This fixes Cloudinary URL generation without
  exposing credentials or contacting the live media account; staging and
  production still fail closed when their real credentials are absent.
- Django check: no issues.
- Production-style deploy check: only the intentionally deferred HSTS include-subdomains/preload warnings. Enable these only after all relevant subdomains are HTTPS.

- Complete Django suite: **501 passed, 1 skipped, 0 failed**.
- Migration drift: **no changes detected**.
- Python dependency consistency: **no broken requirements**.
- Tailwind/vendor build: **passed**; Browserslist advisory metadata is stale but did not fail the build.
- Focused storefront/static regression after enabling manifest storage: **27 passed**.
- Staging-style `check --deploy`: passed with only the intentionally deferred HSTS include-subdomains/preload warnings.
- Earlier local parsing did not prove Render API compatibility. On 2026-07-27 the staging Blueprint was corrected after the current Render specification confirmed that `sync: false` is ignored inside environment groups.
- Full regression after separating safe staging gates: **501 passed, 1 skipped, 0 failed**.

## Staging provisioning preparation - 2026-07-27

- Eight focused deployment-setting/Blueprint regression tests passed.
- Complete Django suite: **533 passed, 1 expected SQLite/PostgreSQL row-lock test skipped, 0 failed**.
- Django checks, migration drift and compilation passed.
- The Blueprint now uses deterministic HTTPS staging origins, persistent `noeviction` Key Value, schema-gated worker/Beat startup and a one-time approved branch configuration hook.
- Outbound email, SMS, Sentry and Daraja credentials are intentionally absent from the infrastructure bootstrap and remain later certification gates.
- No Render resources were created. The private GitHub repository and staging Blueprint exist, but provisioning was deferred on 2026-07-28 because the client-owned Render account has no funded payment method.
- Render CLI/API validation remains required after account authentication because it performs schema, semantic-plan and workspace-conflict validation that local text tests cannot replace.

Gunicorn cannot be meaningfully exercised on this Windows development host. Its process lifecycle, graceful shutdown and health-gated routing remain staging acceptance items on Linux.

## External acceptance still required

- Connect a private Git remote with CI, authenticate Render, validate the Blueprint against the selected workspace, review the live cost summary and explicitly approve resource creation.
- Staging browser journeys and sandbox providers.
- Hosted uptime plus worker/Beat/database/Redis alert and recovery delivery. Repository probes and failure drills are implemented but are not external evidence.
- Managed PITR restore into an isolated database.
- Off-site logical backup and restore, if enabled.
- Load/capacity and external security testing.
