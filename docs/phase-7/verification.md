# Phase 7 verification record

Date: 2026-07-22 (Africa/Nairobi)

```powershell
.\venv\Scripts\python.exe manage.py test --verbosity 1 inventory
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m compileall -q apps config
.\venv\Scripts\python.exe manage.py migrate --noinput
```

Results:

- Inventory workspace tests: 4 passed.
- Complete project tests: 315 passed, 1 skipped.
- Checks: 0 issues.
- Migration drift: none.
- Compilation: passed.
- Local migrations: applied successfully.

The skipped test requires a database with real row-level locking. It must run against PostgreSQL in staging before release.

Browser QA used a disposable SQLite database and two branch-scoped staff accounts. The verified sequence was supplier intake at OTC, transfer request, source approval, dispatch into transit, B03 receipt and completion of an exact physical stock count. The original client logo was also inspected in the responsive storefront hero. The temporary database, staff records and server were removed after the run.
