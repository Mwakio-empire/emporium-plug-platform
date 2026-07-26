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

## Approved branch configuration verification

Date: 2026-07-27 (Africa/Nairobi)

```powershell
.\venv\Scripts\python.exe manage.py test branches.tests --verbosity 1
.\venv\Scripts\python.exe manage.py configure_business_branches --dry-run
.\venv\Scripts\python.exe manage.py configure_business_branches
.\venv\Scripts\python.exe manage.py configure_business_branches
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m compileall -q apps config
.\venv\Scripts\python.exe manage.py test --verbosity 1
```

Results:

- Branch configuration tests: 8 passed.
- Dry run showed the exact approved OTC Mall, S18 and B03 records and rolled back.
- The first real run created OTC Mall and B03 and updated the existing S18 row.
- The second real run updated the same three rows without duplicates.
- Database inspection confirmed exactly one supplier-intake hub (OTC Mall) and one customer pickup branch (S18).
- Complete project suite: 525 passed, 1 expected PostgreSQL row-lock test skipped on SQLite.
- Django checks: 0 issues; migration drift: none; compilation: passed.
