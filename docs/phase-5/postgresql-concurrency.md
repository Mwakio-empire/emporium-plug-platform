# PostgreSQL concurrency verification

SQLite cannot verify row-level locking. Use an isolated PostgreSQL test instance, never production.

## Preconditions

- PostgreSQL staging/test database with permission to create a disposable Django test database.
- Candidate application revision and migrations.
- `DATABASE_URL` points to the isolated PostgreSQL instance.
- No external-provider credentials are needed.

## Commands

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py test inventory.tests.PostgreSQLInventoryConcurrencyTests --verbosity 2
```

Expected: `test_two_simultaneous_sales_cannot_oversell` runs without being skipped; one deduction succeeds, one is blocked, and one unit remains.

Then run the full suite:

```powershell
.\venv\Scripts\python.exe manage.py test --verbosity 1
```

The gate fails if the concurrency test is skipped, both sales succeed, both unexpectedly fail, or remaining stock is not exactly one.
