# Hosting architecture decision

## Recommendation

Use Render in the Frankfurt region for the first client release:

- one public Gunicorn web service;
- one private Celery worker;
- one private Celery Beat process only;
- paid Basic-1gb managed PostgreSQL with point-in-time recovery and 5 GB initial storage;
- persistent Key Value/Redis-compatible service using `noeviction`;
- Cloudinary for catalog images;
- Sentry with default PII disabled;
- optional off-site encrypted `pg_dump` archives in a separate S3 account/bucket.

Render is recommended because its current documented model directly supports health-gated web services, pre-deploy commands, background workers, Key Value and paid PostgreSQL PITR in a reviewable Blueprint. Railway remains viable, but its backup/PITR operating procedure and service configuration would need a separate platform-specific runbook.

## Region decision

On 2026-07-26, the client approved Frankfurt for staging and production. Render
does not currently offer an African region; its available regions are
Frankfurt, Singapore, Oregon, Ohio and Virginia. Frankfurt is the nearest of
those choices to the platform's Kenya-only customer and staff base, so it is
the best starting assumption for lower customer-facing network latency. This
is a geographic inference and must still be confirmed with measured staging
latency from Nairobi before launch.

All web, worker, Beat, PostgreSQL and Key Value resources remain in Frankfurt.
Keeping them together enables Render's regional private networking and avoids
adding public cross-region database/cache calls to every request or task.
Singapore is farther from Nairobi, and the three US regions are farther still;
none offers a compensating business, integration or cost advantage for this
Kenya-only release.

The trade-off is that application and customer data will be processed outside
Kenya, in Germany. The client must address cross-border processing, processor
terms and any required safeguards with qualified Kenyan privacy/legal advice.
Render does not support changing an existing service or database region in
place, so a future move to an African region would require a planned migration.

## Environment separation

Development, test, staging and production must have separate databases, Redis instances, credentials, provider applications/numbers, Sentry environments and storage configuration. Never copy production customer records into development. Staging should use synthetic data and sandbox providers.

## Availability and recovery objectives requiring client approval

Proposed MVP targets—not guarantees until measured:

- RPO: 15 minutes for database loss, using managed PITR; daily off-site logical archive for longer-term recovery.
- RTO: 4 hours during initial MVP operations.
- Web health alert: after two consecutive failures over five minutes.
- Worker/Beat alert: no heartbeat or scheduled-task execution for ten minutes.

The client must approve targets against hosting cost and business tolerance.

## Cost decision

On 2026-07-26, the client approved the cost-conscious production budget. The
approved Blueprint baseline uses three Starter compute services, Starter Key
Value, Basic-1gb PostgreSQL with 5 GB storage, and a Hobby workspace. At the
prices reviewed on that date, the fixed Render infrastructure estimate is
USD 51.50 per month before taxes, exchange-rate differences, bandwidth
overages and external-provider usage. This estimate is a planning figure, not
a guaranteed supplier quotation.

Cloudinary and Sentry should begin on their free tiers and be upgraded only
after measured usage or team-access requirements justify it. SMS, WhatsApp
Business API messaging, M-Pesa transaction charges, domain renewal and
off-site backup storage remain variable or separately billed.
