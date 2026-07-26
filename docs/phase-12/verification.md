# Phase 12 verification

## Automated commands

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe -m compileall -q apps config
.\venv\Scripts\python.exe -m pip check
npm.cmd run build
```

## Recorded results

- Focused security/privacy suite: **27 passed**.
- Complete Django suite: **495 passed, 1 skipped, 0 failed**.
- Django system check: **0 issues**.
- Migration drift check: **no changes detected**.
- Python compile check: **passed**.
- Python dependency consistency (`pip check`): **no broken requirements**.
- Tailwind/vendor asset build: **passed**. Browserslist reported its advisory database as stale; this did not fail the build.
- Production-style `check --deploy`: only `security.W005` and `security.W021`. HSTS subdomain coverage and preload are deliberately false until every client subdomain is verified HTTPS; enabling them prematurely is difficult to reverse.

## Manual/browser acceptance checklist

- **Passed:** public storefront and privacy pages render under enforced CSP with no browser console errors.
- **Passed:** privacy operations renders in an isolated super-admin QA session.
- **Passed:** inventory intake's external script changes the line count from one to two under CSP.
- **Passed:** management dashboard metrics load and the timeframe changes to `today` through HTMX/external JavaScript with no console errors.
- **Passed by automated tests:** customer privacy form rejects a wrong password, accepts a valid request and prevents duplicate open requests.
- **Passed by automated tests:** customer export is password-confirmed, `private, no-store`, account-scoped and excludes credential fields.
- **Passed by automated tests:** staff/customer privacy-operations denial and super-admin password re-authentication.
- **Passed by automated tests:** invalid product files and unauthenticated inbound SMS are rejected without mutation.

Browser testing used a separate SQLite QA database with synthetic credentials; it did not alter a real user password, submit a real order or contact an external provider.

## Explicit exclusions

- No live provider call, real customer data, real payment, penetration test or production attack simulation is authorized by this phase.
- External advisory metadata scan, WAF/edge checks, backup access and staging infrastructure validation remain separate gates.
