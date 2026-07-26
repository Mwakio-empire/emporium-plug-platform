# Phase 9 verification

Commands:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test apps.marketing --verbosity 1
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe -m compileall -q apps config
npm.cmd run build
```

Recorded on 22 July 2026 after activation of the approved product-level return policy:

- Marketing focused suite: 47 passed.
- Combined marketing/catalog suite: 63 passed.
- Full suite: 459 passed, one intentional skip, zero failures.
- Django checks and migration drift: clean.
- Production asset build: pass.
- Browser acceptance: pass.

PostgreSQL concurrency testing and client UAT remain required before production approval.
