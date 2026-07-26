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

- Focused health/backup suite: 6 passed.
- Static production build: 177 files copied and 511 post-processed after resolving the Cloudinary override conflict.
- Django check: no issues.
- Production-style deploy check: only the intentionally deferred HSTS include-subdomains/preload warnings. Enable these only after all relevant subdomains are HTTPS.

- Complete Django suite: **501 passed, 1 skipped, 0 failed**.
- Migration drift: **no changes detected**.
- Python dependency consistency: **no broken requirements**.
- Tailwind/vendor build: **passed**; Browserslist advisory metadata is stale but did not fail the build.
- Focused storefront/static regression after enabling manifest storage: **27 passed**.
- Staging-style `check --deploy`: passed with only the intentionally deferred HSTS include-subdomains/preload warnings.
- Production and staging Blueprints: parsed successfully; all resources resolve to Frankfurt and use isolated names.
- Full regression after separating safe staging gates: **501 passed, 1 skipped, 0 failed**.

Gunicorn cannot be meaningfully exercised on this Windows development host. Its process lifecycle, graceful shutdown and health-gated routing remain staging acceptance items on Linux.

## External acceptance still required

- Render CLI/API Blueprint validation and sync; no usable Git remote or authenticated Render session is currently available.
- Staging browser journeys and sandbox providers.
- Continuous uptime plus worker/Beat/database/Redis alerts.
- Managed PITR restore into an isolated database.
- Off-site logical backup and restore, if enabled.
- Load/capacity and external security testing.
