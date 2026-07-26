# Phase 10 verification

Commands:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test apps.reports apps.analytics --verbosity 1
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe -m compileall -q apps config
npm.cmd run build
```

Recorded final results on 22 July 2026:

- Phase 10 reconciliation/permission/schedule tests: 11 passed.
- Reports and analytics suite: 59 passed.
- Full project suite: 470 passed, one intentional skip, zero failures.
- Django checks, migration drift and syntax compilation: clean.
- Production asset build: pass.
- Generated PDF: valid one-page A4; rendered to PNG and visually inspected with no clipping or overlap.
- Browser acceptance: all-branch KES 7,000 reconciled across two branches; S18 filtering returned KES 2,500 without OTC leakage; CSV link and report definitions were present.
