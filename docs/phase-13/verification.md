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
- Static production build: 177 files copied and 511 post-processed after resolving the Cloudinary override conflict.
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
