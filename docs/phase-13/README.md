# Phase 13: production engineering

Status: repository-level production engineering is implemented and locally verified. No external infrastructure has been created and production is not approved.

## Delivered

- Explicit development, test, staging and production environment identity.
- Gunicorn production server and WhiteNoise compressed/hashed static assets.
- Dependency-aware readiness, process-only liveness and Beat-to-worker operational health endpoints.
- Request correlation IDs and structured JSON production logs.
- HTTPS site/origin, proxy, host, privacy, Redis, notification and persistent-image fail-fast configuration.
- Render Blueprint recommendation for separate web, Celery worker, Celery Beat, paid PostgreSQL and persistent no-eviction Key Value services.
- A separate `render.staging.yaml` Blueprint with isolated names, sandbox M-Pesa, synthetic data and real outbound messaging disabled.
- Safe pre-deploy migrations and health-gated web deployment definition.
- PostgreSQL `pg_dump` custom-format off-site backup service with checksum, encryption and no local fallback.
- Deployment, rollback, backup/restore and incident operating procedures.
- Bounded capacity-probe tooling, CI security scans and independent-assessment rules of engagement.

## External release gates

- Approval of the custom domain and named operational owners. Frankfurt and the cost-conscious Render budget were approved on 2026-07-26.
- A green GitHub Actions run on the final release revision. The client-owned
  remote and CLI access are verified; the final unpushed batch still requires
  remote CI execution.
- A funded Render account for Blueprint sync. Workspace validation succeeded,
  but Render requires client-owned payment information before creating the
  proposed resources.
- Separate staging and production projects/databases/secrets.
- Paid managed PostgreSQL PITR enabled and a controlled restore proven.
- S3 lifecycle/retention and least-privilege backup credentials if logical off-site backups are enabled.
- Hosted uptime, web, worker, Beat, database and Redis alerts configured and tested. Repository-level probes and failure drills are implemented, but no hosted alert delivery is claimed.
- Staging load test, external security assessment and provider certification.
- Client privacy/legal decisions from Phase 12.
- Client UAT and explicit live M-Pesa authorization.

Committing `render.yaml` does not provision or charge for infrastructure. The approved planning baseline is USD 51.50/month before taxes, exchange-rate differences, overages and external-provider usage; recheck supplier pricing before Blueprint sync.

The staging Blueprint uses a smaller Basic-256mb database and otherwise keeps
the production process topology. Its fixed estimate is USD 38.50/month while
continuously active. Render bills compute/storage proportionally, so staging
may be provisioned for controlled acceptance windows, but it must be scaled to
the production database size before representative load testing. This staging
cost is documented but has not yet been authorized or incurred.

See [architecture decision](architecture.md), [deployment runbook](deployment-runbook.md), [media runbook](media-storage-runbook.md), [monitoring runbook](monitoring-runbook.md), [load/security runbook](load-security-runbook.md), [backup/restore runbook](backup-restore.md), [traceability](traceability.md), [defect register](defect-register.md), [verification](verification.md), and [image-search decision](deferred-image-search.md).

Before migration or production approval, execute the consolidated
[manual acceptance guide](../testing/manual-uat-guide.md) and retain a completed
[results record](../testing/manual-uat-results-template.md).
