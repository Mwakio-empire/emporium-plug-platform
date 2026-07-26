# Phase 11 verification

Run from the repository root:

```powershell
.\venv\Scripts\python.exe manage.py test apps.notifications apps.inventory apps.users apps.orders apps.logistics apps.payments apps.reports --verbosity 1
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m compileall -q apps config
.\venv\Scripts\python.exe -m pip check
npm.cmd run build
npm.cmd audit
```

Browser acceptance covers:

- authorized manager access to the notification operations workspace;
- masking of recipient details and absence of rendered message content;
- visibility of a branch-owned manual follow-up;
- evidence-note validation and successful audited resolution;
- branch isolation and unauthorized-role denial (also automated).

Real provider delivery is intentionally excluded from automated and browser tests. Use non-customer test numbers and an explicitly invoked provider sandbox plan before any live activation.

## Recorded result: 22 July 2026

- Full Django suite: 477 tests passed; one intentional skip.
- Notification and low-stock focused suite: 17 tests passed.
- Django system check: no issues.
- Migration drift check: no changes detected.
- Notification migrations `0001` through `0003`: applied successfully to the development database.
- Python compile check: passed.
- Python dependency consistency: no broken requirements.
- Frontend production build: passed.
- Browser acceptance: passed; see `browser-acceptance.md`.
- `npm audit`: not completed because the environment denied transmitting dependency metadata to the external npm advisory service. No vulnerability result is claimed.
