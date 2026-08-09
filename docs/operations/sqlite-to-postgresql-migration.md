# SQLite to PostgreSQL migration record

## Status

The current local SQLite development dataset was migrated to PostgreSQL 17 on
2026-07-30. This is local migration evidence, not production migration approval.
The original SQLite database, its verified backup and the older PostgreSQL sandbox
database were preserved.

## Data sources and targets

| Store | Purpose | Result |
|---|---|---|
| `db.sqlite3` | Current local development source | Preserved |
| `emporium_sandbox` | Older PostgreSQL sandbox data | Preserved; not merged |
| `emporium_migration_rehearsal` | First fixture import | Passed |
| `emporium_current` | Migration candidate | Passed |
| `emporium_restore_test` | Native-backup restore test | Passed |

The older PostgreSQL database was not selected as the source because it contained
one `Sandbox Test Item` and 13 sandbox orders, while SQLite contained the current
five-product visual catalogue and four recent manual-test orders. No orders were
merged or silently discarded.

## Recovery artifacts

All artifacts are under the Git-ignored `backups/local/` directory and may contain
personal or authentication data. They must not be uploaded or committed.

- `db.sqlite3.20260730-172726.backup`: SQLite online backup.
- `sqlite-business-data.20260730-173346.json`: first-party fixture; 289 objects
  across 25 models.
- `emporium_current.20260730-173648.dump`: PostgreSQL custom-format archive;
  707 restore-list entries.

The SQLite backup passed `PRAGMA integrity_check` and contained zero foreign-key
problems. The PostgreSQL archive was listed with `pg_restore --list` and restored
into `emporium_restore_test`.

## Migration method

1. Create and hash an online SQLite backup.
2. Verify SQLite integrity, foreign keys and headline record counts.
3. Compare the migration-seeded Kenya county reference data in both engines.
4. Export first-party business models with `dumpdata`, excluding
   `logistics.kenyacounty` because its 47 code/name records had identical hashes.
5. Migrate a fresh rehearsal PostgreSQL database.
6. Load the fixture into rehearsal and compare every exported model count.
7. Test PostgreSQL sequence advancement inside a rolled-back transaction.
8. Refuse the real import unless every fixture model in `emporium_current` is
   empty.
9. Load the rehearsed fixture into `emporium_current` and repeat count/check gates.
10. Create a custom-format `pg_dump`, restore it to a new database and compare
    counts again.

## Verified record counts

| Record | SQLite | Rehearsal | Current | Restored backup |
|---|---:|---:|---:|---:|
| Users | 8 | 8 | 8 | 8 |
| Products | 5 | 5 | 5 | 5 |
| Product variants | 27 | 27 | 27 | 27 |
| Stock rows | 28 | 28 | 28 | 28 |
| Orders | 4 | 4 | 4 | 4 |
| Migration records | 111 | 111 | 111 | 111 |

All 25 exported model counts matched. One active super-admin account exists in the
migrated database. Password/OTP values and personal details were not printed.

## PostgreSQL defects found and corrected

The first complete PostgreSQL run executed 608 tests and reported 48 errors.
SQLite had hidden an unsupported lock shape: `SELECT FOR UPDATE` was applied to
the nullable side of outer joins. Affected flows included transfers, returns,
customer cancellation, scheduled reports, parcel dispatch and low-stock scanning.

The affected queries now use `select_for_update(of=('self',))`, locking the row
being mutated while related nullable rows remain read-only. Stock and other
mutable records retain their own explicit locks.

Verification after correction:

- Focused affected PostgreSQL suites: 130/130 passed.
- PostgreSQL inventory race test: passed and was not skipped.
- Complete PostgreSQL suite: 608/608 passed.
- Django system and migration-drift checks: passed.
- Redis Django-cache round trip: passed.
- Celery Redis broker connection: passed.
- Beat published and the worker executed the isolated heartbeat in 55 ms.

## Rendered smoke test

The migrated application was served separately on port 8002 and checked in the
in-app browser without changing the SQLite comparison server on port 8001.

- Desktop and 390 px mobile storefront rendered without relevant console errors.
- Five products and migrated images rendered.
- Guest wishlist state survived reload.
- A 24 cm frying-pan variant added to cart at KES 1,450.
- Checkout displayed the same item/total and selected S18 pickup by default.
- Town delivery remained an explicit WhatsApp-assisted path.
- Direct `/admin/` access redirected an unauthenticated user to the unified login.

No order was submitted and no provider message or M-Pesa request was sent.

## Remaining migration gates

- Manually sign in with the migrated super-admin and verify staff 2FA.
- Exercise critical browser journeys against PostgreSQL, including a controlled
  sandbox checkout, POS sale, transfer and reconciliation.
- Replace the temporary manually created containers with the checked-in Compose
  named-volume setup only during a backed-up maintenance window.
- Repeat migration, backup and restore evidence in funded staging before launch.
- Keep SQLite and all migration artifacts until client acceptance is recorded.
