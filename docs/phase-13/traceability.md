# Phase 13 traceability

| Requirement | State | Evidence |
|---|---|---|
| Development/test/staging/production configuration | Implemented; external environments unprovisioned | `ENVIRONMENT`, separate staging/production gates, `render.staging.yaml`, `render.yaml` and runbook |
| PostgreSQL production database | Defined; external gate | Approved Basic-1gb Blueprint database with 5 GB initial storage and `DATABASE_URL` reference |
| Redis secure/persistent broker | Defined; external gate | Private Key Value, `noeviction`, paid plan |
| Celery worker and Beat | Defined; external gate | Separate Blueprint workers; exactly one Beat service |
| Static assets | Complete and locally verified | WhiteNoise manifest/compression and successful `collectstatic` |
| Persistent media | Complete at code/provider level; staging redeploy proof pending | Staging and production fail closed without Cloudinary. A synthetic write/delivery/delete round trip passed on 2026-07-28; the deployment persistence check awaits funded staging. |
| HTTPS/cookies/hosts/CSRF/proxy | Complete at config level | Fail-fast settings and deploy check |
| Secrets | Defined; external gate | No values are committed. Staging bootstrap disables external integrations; later provider items add secrets directly or through a dashboard-managed secret group, never ignored `sync: false` group entries. |
| Structured logging/correlation | Complete and verified | JSON formatter, request ID middleware/tests |
| Sentry PII/release controls | Complete at config level; external gate | Django/Celery integrations, environment/release tags, zero default sampling and `send_default_pii=False`; DSN/alerts require staging |
| Health/readiness | Complete and verified | `/health/live/`, `/health/ready/`, dependency failure tests and no-store responses |
| Worker/Beat operational heartbeat | Complete and verified locally | Beat schedules a one-minute task; `/health/operations/` fails after a stale combined Beat/broker/worker path |
| Hosted alert delivery | External gate | Monitoring runbook; Render/Sentry/external monitors require funded staging and named recipients |
| Safe staging privacy/notifications | Complete and locally verified | Staging permits unapproved synthetic-data wording and suppressed console delivery; production fail-closes on invalid privacy/provider configuration |
| Safe migrations/low-downtime deploy | Defined; staging proof required | `preDeployCommand`, readiness health gate, rollback runbook |
| PostgreSQL-native backups | Complete and verified locally at application layer | `pg_dump` custom format, streaming checksum, S3 encryption, temporary-file cleanup and tests |
| Uploaded archive verification | Complete and verified locally | `verify_database_backup` requires encryption, SHA-256 equality and a readable `pg_restore --list` catalog |
| Managed PITR | External gate | Paid host configuration and restore evidence required |
| Restore testing | Blocked on managed staging PostgreSQL | `backup-restore.md` procedure |
| RPO/RTO | Proposed; client decision | Architecture ADR |
| Bounded load-test tooling | Complete and locally verified | GET-only probe with remote-target authorization, redirect prevention, safety caps, threshold exit and unit tests |
| Production-sized capacity evidence | External gate | Funded staging, approved workload model and `load-security-runbook.md` |
| Independent penetration test/retest | External gate | Written rules of engagement and independent assessor required; local scans are not certification |
| Render Blueprint validation | Complete except funding acceptance | Both files pass the pinned 2026-07-28 Render schema. Authorized workspace validation returned only `need_payment_info` for the five paid resources in each Blueprint. |
| Private repository and CI | Corrected locally; remote rerun pending | GitHub CLI access and the client-owned remote were verified. Failed run `30362283936` identified two Cloudinary URL-generation errors; deterministic isolated test media configuration now passes those tests and the complete local suite. |
| Deployment/incident runbooks | Complete as repository artifacts | Phase 13 documentation |
