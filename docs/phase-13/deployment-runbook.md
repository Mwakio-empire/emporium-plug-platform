# Deployment and rollback runbook

## First staging deployment

1. Review `render.staging.yaml`, current pricing, Frankfurt data-location implications and service names.
2. Sync `render.staging.yaml` separately. Do not sync `render.yaml`, point a production domain or use production provider credentials during staging acceptance.
3. The staging Blueprint contains no `sync: false` entries inside its environment group because Render ignores that combination. Its initial infrastructure bootstrap deliberately disables outbound email/SMS, Sentry and Daraja credentials; configure each only in its dedicated certification item.
4. Keep `PRIVACY_NOTICE_APPROVED` false in staging and use synthetic data only. Enter the same client-owned `CLOUDINARY_URL` secret for web, worker and Beat when Render prompts during initial Blueprint creation. For an existing Blueprint, add it manually to all three services because Render ignores newly added `sync: false` entries on later syncs.
5. Confirm `DATABASE_URL` is PostgreSQL and `REDIS_URL` uses the private Key Value connection.
6. Deploy. The web pre-deploy command runs migrations before traffic switches; `/health/ready/` must return 200.
7. Verify the one-time initial deploy hook created the approved OTC Mall/S18/B03 records. Also run `python manage.py configure_business_branches --dry-run` as evidence. Do not seed staff, opening balances or customer data.
8. Run `python manage.py verify_cloudinary_media --confirm-remote-write`, verify product-image upload in the staff UI, redeploy, and confirm the image still renders. Then verify web, worker and Beat logs, static assets and all critical browser journeys.
9. Configure external uptime monitoring of `/health/live/` and `/health/operations/`; keep `/health/ready/` for deployment/readiness decisions. Execute the monitoring runbook's worker, Beat, database and Key Value failure/recovery drills.
10. Configure Sentry Django/Celery release/environment tagging and alerts without PII.
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
