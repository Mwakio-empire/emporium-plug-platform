# Phase 8 verification

Run from the repository root:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test apps.logistics apps.orders apps.notifications
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe -m compileall -q apps config
npm.cmd run build
```

Browser acceptance must cover: staff starts and completes packing; S18 staff marks pickup ready and sees the deadline; pickup code collection; manager assigns an available same-branch rider; customer sees delivery/pickup progress; storefront logo, orange/blue theme, mobile navigation, footer and conditional WhatsApp CTA.

Provider calls remain mocked during ordinary tests. Real SMS, WhatsApp and payments require separately authorized sandbox/production procedures.

## Recorded result — 22 July 2026

- Django system check: pass, no issues.
- Migration drift check: pass, no changes detected.
- Full default suite: 443 tests passed, 1 intentional skip, 0 failures.
- Phase 8 focused suite: 12 tests passed.
- Python dependency check: no broken requirements.
- Tailwind/vendor production asset build: pass.
- Browser acceptance: pass for the journeys recorded in `browser-acceptance.md`.

Two missing test-package markers were added during verification. This raised default-suite discovery from 315 tests; the current 443-test result is the valid release-gate count.
