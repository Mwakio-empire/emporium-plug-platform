# Monitoring and alert-response runbook

## Monitoring surfaces

| Surface | What it proves | Consumer | Initial alert rule |
|---|---|---|---|
| `/health/live/` | Gunicorn can answer HTTP without revealing dependency state. | Independent external uptime monitor. | Alert after two consecutive failures within five minutes; notify again on recovery. |
| `/health/ready/` | The web process can query PostgreSQL and read/write Key Value. | Render's web-service health check. | Render removes/restarts unhealthy instances; enable failure and recovery email notifications. |
| `/health/operations/` | PostgreSQL and Key Value are available and a Beat-scheduled heartbeat was executed by a Celery worker within ten minutes. | Independent external monitor. | Alert after two consecutive failures; do not use this endpoint as the web routing health check. |
| Sentry Django/Celery integration | Unhandled web/task errors, tagged by environment and Git release. | Engineering/operations owners. | Alert on a new high-priority issue and repeated server errors; confirm a named owner and escalation destination. |
| Render service/datastore metrics | CPU, memory, database storage/connections and Key Value activity/connections. | Daily operations review and capacity owner. | Record warning/critical thresholds after staging baseline measurements; do not invent production thresholds from local data. |

All health responses use `Cache-Control: no-store` and return only component
names, never connection strings, credentials or exception messages.

## Why the asynchronous probe is combined

Celery Beat schedules `core.tasks.record_async_pipeline_heartbeat` every minute.
The worker writes the timestamp to shared Key Value only after it executes the
task. A fresh timestamp therefore proves that Beat, the broker and at least one
worker completed the full path. A stale timestamp identifies the asynchronous
pipeline as unavailable; logs and Render process state determine whether Beat,
the broker or the worker caused it. This avoids falsely claiming the application
can distinguish them from one shared heartbeat.

## Staging configuration

1. Keep Render's `healthCheckPath` set to `/health/ready/`.
2. Set `ASYNC_HEARTBEAT_MAX_AGE_SECONDS=600` on web, worker and Beat through the
   shared environment group.
3. Create two independent HTTPS monitors: `/health/live/` and
   `/health/operations/`. Use synthetic labels and no customer data.
4. Enable Render workspace email notifications for all failures and recoveries;
   verify the recipient list contains at least two named operational owners.
5. Create separate Sentry staging and production environments. Configure
   `SENTRY_DSN`, keep `SENTRY_SEND_DEFAULT_PII=False`, and use
   `RENDER_GIT_COMMIT` or `SENTRY_RELEASE` for release correlation. Leave tracing
   and profiling at zero until an approved sampling decision exists.
6. Review PostgreSQL storage/connections and Key Value memory/connections in
   Render. Set capacity thresholds only after representative staging load; name
   the person responsible for scaling.
7. Record every destination, owner, threshold, test time, alert arrival time and
   recovery arrival time in the release evidence package.

## Required failure drills

Run these only in staging with synthetic data:

1. Stop the web process or point the external uptime monitor temporarily at an
   approved failing test path. Confirm the alert and recovery messages.
2. Stop only Beat. Wait up to the configured ten-minute maximum and confirm
   `/health/operations/` alerts while `/health/live/` remains healthy. Restart
   Beat and confirm recovery after the worker executes a new heartbeat.
3. Stop only the worker and repeat the previous check. Beat will enqueue but no
   process will execute the heartbeat.
4. Suspend or firewall the staging Key Value instance using the provider's safe
   test procedure. Confirm readiness and operations fail without exposing the
   URL or password, then restore and verify recovery.
5. Use an isolated database failure procedure approved by the host. Confirm
   readiness and operations fail, then restore connectivity and reconcile the
   application before accepting recovery.
6. As an authorized super admin, invoke the existing Sentry diagnostic endpoint
   once in staging. Confirm environment/release tags and that no PII is attached.

Do not perform database/Key Value outage drills against production during launch.
Item 9 is not externally complete until every alert and recovery path above has
retained evidence from the funded staging environment.
