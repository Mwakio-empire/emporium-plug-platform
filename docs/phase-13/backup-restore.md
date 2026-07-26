# PostgreSQL backup and restore runbook

## Required layers

1. Paid host-managed PostgreSQL point-in-time recovery for the short RPO window.
2. Optional encrypted off-site `pg_dump` custom-format archives for independent/longer retention.
3. Versioned application code, migrations and environment-variable inventory.

Django `dumpdata`, local media files and an untested archive are not disaster recovery.

## Logical backup

Enable only after creating a dedicated least-privilege S3 identity, private bucket, encryption policy, versioning/lifecycle and monitoring:

```powershell
$env:BACKUP_ENABLED='True'
.\venv\Scripts\python.exe manage.py create_database_backup
```

Production scheduling should use a single platform cron job. The application Beat schedule intentionally does not run backups. Alert on every missed/failed backup and keep the bucket separate from the application account where practical.

## Controlled restore test

1. Provision an empty isolated PostgreSQL database of a compatible major version.
2. Download one archive and verify its SHA-256 against object metadata.
3. Run `pg_restore --list archive.dump` and review contents.
4. Restore only into the empty isolated target:

   `pg_restore --no-owner --no-privileges --exit-on-error --dbname TARGET_URL archive.dump`

5. Run migrations/checks, then verify user counts, branch inventory totals, order/payment reconciliation and immutable audit history.
6. Record archive key, checksum, PostgreSQL/client versions, duration, result and tester.
7. Destroy the isolated restored database according to the approved test-data handling procedure.

Restore testing is not complete until this procedure succeeds against the selected managed host. Never place a production database URL in chat, source control or test output.
