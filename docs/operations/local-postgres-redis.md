# Local PostgreSQL and Redis

This project uses PostgreSQL as durable application storage and Redis for cache,
rate-limit state, Celery task delivery and short-lived coordination. Redis is not
the source of truth for orders, payments or inventory.

## Safety status for this workstation

Two manually created containers provide the active local services:

- `emporium-sandbox-postgres`: PostgreSQL container port `5432` is exposed as
  Windows loopback port `55432`.
- The old `emporium-sandbox-redis` definition is retained but is no longer the
  recommended runtime because its host-port mapping can conflict with Windows.
  The authenticated Compose Redis service uses loopback port `56379` by default.

Their Docker volumes must not be removed. The PostgreSQL server now contains four
deliberately separate databases:

- `emporium_sandbox`: older sandbox-only records retained for investigation.
- `emporium_current`: verified migration of the current SQLite development data.
- `emporium_migration_rehearsal`: rehearsal import used before the real migration.
- `emporium_restore_test`: controlled restore of the PostgreSQL-native backup.

On 2026-07-31, Windows dynamically reserved host port `5432`. The PostgreSQL
container definition was safely replaced with one bound to `127.0.0.1:55432`,
while retaining the same persistent volume. The previous stopped definition is
named `emporium-sandbox-postgres-port5432-backup`; do not start it alongside the
replacement because both definitions reference the same PostgreSQL data volume.

The checked-in startup helper preserves the migrated PostgreSQL container when it
exists and starts only the reproducible Compose Redis service. Do not replace the
PostgreSQL container or its volume without a verified backup and restore plan.

## Reproducible setup

1. Copy `.env.docker.example` to `.env.docker.local`.
2. Replace both example passwords with different, randomly generated local-only
   values. Never reuse production, email, M-Pesa or personal passwords.
3. Start the services:

   ```powershell
   docker compose --env-file .env.docker.local -f compose.local.yml up -d
   ```

4. Verify them:

   ```powershell
   docker compose --env-file .env.docker.local -f compose.local.yml ps
   ```

The Compose services bind only to the Windows loopback interface. Their named
volumes survive ordinary container restarts and recreation. `docker compose down`
keeps those volumes; `docker compose down --volumes` deletes them and must not be
used against valuable data.

## Application connection

Django reads `DATABASE_URL`, `DATABASE_CONN_MAX_AGE` and `REDIS_URL` from `.env`.
For local development, use host port `55432` in the PostgreSQL URL for the isolated development database
and an authenticated Redis URL matching `.env.docker.local`. Keep
`DATABASE_CONN_MAX_AGE=0` for local commands and tests unless connection behaviour
is itself under test.

Do not point migrations or automated tests at production. Django creates a
disposable test database derived from the configured local PostgreSQL database.

## Daily mental model

- Docker Desktop runs the Linux container engine.
- A container is the running PostgreSQL or Redis process.
- An image is the pinned software package used to create a container.
- A volume holds persistent database/cache files outside a container's writable
  layer.
- Compose is the checked-in recipe that recreates the same local services.

SQLite remains a preserved rollback source. The active migration candidate is
`emporium_current`; see `docs/operations/sqlite-to-postgresql-migration.md` for the
completed rehearsal, count comparison, backup/restore and browser evidence.

## Current workstation commands

After starting Docker Desktop and waiting for its engine, start the services and
the Django development server with:

```powershell
.\scripts\start_local_postgres.ps1
```

The helper detects and preserves `emporium-sandbox-postgres` when present. It
starts an authenticated Compose Redis service on port `56379`, reads credentials
without displaying them, connects Django to `emporium_current` through port
`55432`, applies migrations, runs Django system checks and serves the site at
`http://127.0.0.1:8002/`. On a fresh workstation without the preserved container,
it starts both services from `compose.local.yml`. Keep that terminal open while
using the site.

Confirm service readiness:

```powershell
docker exec emporium-sandbox-postgres pg_isready
docker compose --env-file .env.docker.local -f compose.local.yml ps redis
```

The `pg_isready` output shows container port `5432`; this is expected. Windows and
Django reach that same service through host port `55432`.

Do not run more than one Celery Beat process. Beat includes order cancellation,
pickup reminders, low-stock alerts and report dispatch in addition to its health
heartbeat. Use the development-safe notification provider during local testing.
