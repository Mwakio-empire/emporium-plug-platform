# Phase 6 verification record

Date: 2026-07-22 (Africa/Nairobi)

## Automated commands

```powershell
.\venv\Scripts\python.exe manage.py test --verbosity 1 core.tests core.tests_pos core.tests_pos_discount_audit core.tests_phase6_pos orders.tests_pos_void reports.tests
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m compileall -q apps config
```

Results:

- Focused suite: 62 tests, all passed.
- Full suite: 295 tests passed, 1 skipped.
- System checks: 0 issues.
- Migration drift: none.
- Compilation: passed.

## Browser journey

An isolated disposable SQLite database and development-only local-memory cache were used. No real customer, provider or payment data was contacted.

Verified sequence:

1. Staff password authentication and mandatory OTP screen.
2. Open shift with opening cash.
3. Search `Browser Soap`; only branch stock appeared with the correct KES 150 price.
4. Add the simple product; cart and customer display both showed one item and KES 150.
5. Enter a test phone, select cash, tender KES 200 and complete the sale.
6. Confirm KES 50 change and an authorized receipt link.
7. Confirm the cart and `Complete Sale` control disappeared immediately after success.
8. Close the shift with the exact expected cash and confirm the page returned to `Open your shift before selling`.

Browser QA found POS-012 through POS-015; each was corrected and the relevant journey repeated successfully.

## Deferred evidence

- PostgreSQL locking/concurrency behavior must run in staging; the SQLite-incompatible test is the one skipped test.
- Receipt PDF download was verified through Django response tests. The in-app browser blocked direct PDF navigation at the client layer, so no claim is made about a particular kiosk browser PDF viewer.
- Barcode scanners, receipt printers and fiscal devices require real hardware acceptance testing.
