# Phase 13 traceability

| Requirement | State | Evidence |
|---|---|---|
| Development/test/staging/production configuration | Implemented; external environments unprovisioned | `ENVIRONMENT`, separate staging/production gates, `render.staging.yaml`, `render.yaml` and runbook |
| PostgreSQL production database | Defined; external gate | Approved Basic-1gb Blueprint database with 5 GB initial storage and `DATABASE_URL` reference |
| Redis secure/persistent broker | Defined; external gate | Private Key Value, `noeviction`, paid plan |
| Celery worker and Beat | Defined; external gate | Separate Blueprint workers; exactly one Beat service |
| Static assets | Complete and locally verified | WhiteNoise manifest/compression and successful `collectstatic` |
| Persistent media | Provider gate | Production requires Cloudinary. Initial staging may explicitly use ephemeral media only until item 11; production rejects that escape hatch. |
| HTTPS/cookies/hosts/CSRF/proxy | Complete at config level | Fail-fast settings and deploy check |
| Secrets | Defined; external gate | No values are committed. Staging bootstrap disables external integrations; later provider items add secrets directly or through a dashboard-managed secret group, never ignored `sync: false` group entries. |
| Structured logging/correlation | Complete and verified | JSON formatter, request ID middleware/tests |
| Sentry PII controls | Complete at config level; external gate | `send_default_pii=False`; DSN/alerts require staging |
| Health/readiness | Complete and verified | `/health/live/`, `/health/ready/`, dependency failure tests |
| Uptime/worker alerts | Documented; external gate | Deployment runbook |
| Safe migrations/low-downtime deploy | Defined; staging proof required | `preDeployCommand`, readiness health gate, rollback runbook |
| PostgreSQL-native backups | Complete and verified locally at application layer | `pg_dump` custom format, streaming checksum, S3 encryption, temporary-file cleanup and tests |
| Uploaded archive verification | Complete and verified locally | `verify_database_backup` requires encryption, SHA-256 equality and a readable `pg_restore --list` catalog |
| Managed PITR | External gate | Paid host configuration and restore evidence required |
| Restore testing | Blocked on managed staging PostgreSQL | `backup-restore.md` procedure |
| RPO/RTO | Proposed; client decision | Architecture ADR |
| Capacity/load testing | Deferred to stable staging | Explicit release gate |
| Deployment/incident runbooks | Complete as repository artifacts | Phase 13 documentation |
