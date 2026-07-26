# Deployment and rollback runbook

## First staging deployment

1. Review `render.staging.yaml`, current pricing, Frankfurt data-location implications and service names.
2. Sync `render.staging.yaml` separately. Do not sync `render.yaml`, point a production domain or use production provider credentials during staging acceptance.
3. Enter every `sync: false` value in the dashboard. Use unique staging secrets and sandbox Daraja/Africa's Talking.
4. Keep `PRIVACY_NOTICE_APPROVED` false in staging and use synthetic data only. Production intentionally fails startup until approved controller/privacy details and a real outbound notification provider are configured.
5. Confirm `DATABASE_URL` is PostgreSQL and `REDIS_URL` uses the private Key Value connection.
6. Deploy. The web pre-deploy command runs migrations before traffic switches; `/health/ready/` must return 200.
7. Run `python manage.py configure_business_branches --dry-run`, verify the approved OTC Mall/S18/B03 output, then run `python manage.py configure_business_branches`. Do not seed staff, opening balances or customer data.
8. Verify web, worker and Beat logs, static assets, Cloudinary upload and all critical browser journeys.
9. Configure external uptime monitoring of `/health/live/`; use `/health/ready/` for deployment/readiness decisions.
10. Configure Sentry release/environment tagging and alerts without PII.
11. Run load, security, backup/restore and provider sandbox acceptance before production approval.
12. Scale staging PostgreSQL to Basic-1gb before representative production-capacity testing, then record the tested sizes with the results.

## Routine release

1. CI must pass tests, migration drift, compilation, dependency consistency and `collectstatic`.
2. Review migrations for locks/data rewrites and define rollback compatibility.
3. Take/confirm a recoverable database point immediately before high-risk migrations.
4. Deploy staging, run smoke tests, then approve production deployment.
5. Monitor readiness, error rate, latency, queue depth, failed tasks, database connections and payment callbacks.
6. Record release version, operator, migration list and verification outcome.

## Rollback

1. Stop/disable the faulty release or redeploy the last known-good commit.
2. Do not blindly reverse a data migration. Determine whether the previous application is schema-compatible.
3. If data was corrupted, restore PITR into a new database, validate it in isolation, then switch services to it.
4. Reconcile orders, payments, inventory and audit continuity before reopening sales.
5. Record incident timeline and corrective action. Rotate credentials if exposure is suspected.

Never run a destructive database restore against the active production database.
