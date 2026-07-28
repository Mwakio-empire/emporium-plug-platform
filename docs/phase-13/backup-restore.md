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

Copy the returned object key into the verification command; do not copy a database
URL, storage credential or checksum into chat:

```powershell
.\venv\Scripts\python.exe manage.py verify_database_backup --object-key "<exact object key printed by create_database_backup>"
```

Verification downloads to a temporary file, requires approved S3 server-side
encryption, compares SHA-256 metadata in constant time and requires
`pg_restore --list` to parse the archive. The temporary file is removed on both
success and failure. This proves archive integrity and readability only; it does
not replace a controlled restore.

Production scheduling should use a single platform cron job. The application
Beat schedule intentionally does not run backups. Alert on every missed/failed
backup and verification, and keep the bucket in a separate account where
practical. The client must approve retention before launch; configure bucket
versioning, denied public access, lifecycle retention and deletion protection
at the storage layer. Never rely on application code alone to prevent backup
deletion.

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

## Acceptance evidence

Record all of the following in the release evidence package:

- managed PITR status and earliest selectable recovery point;
- source database and isolated restore identifiers, without credentials;
- backup object key, SHA-256, encryption mode and retention class;
- backup start/end, restore start/end and integrity/reconciliation results;
- measured RPO and RTO compared with the proposed 15-minute RPO and four-hour
  RTO; and
- operator, reviewer, date, tested Git revision and cleanup confirmation.

The 15-minute/four-hour targets remain proposed until the client accepts them.
Item 8 remains a critical launch blocker until both the managed PITR exercise
and one logical archive restore succeed on funded staging infrastructure.
