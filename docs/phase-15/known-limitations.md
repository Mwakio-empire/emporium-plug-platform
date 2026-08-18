# Known limitations

These are accepted facts as of 2026-07-26, not hidden defects.

## Production and external proof

- Render staging/production resources have not been provisioned. The private repository and staging Blueprint are prepared, but deployment was explicitly deferred on 2026-07-28 because the client-owned Render account requires a funded payment method. This is a mandatory end-of-project reminder and launch blocker.
- Both Blueprints pass Render's official schema locally. Authorized Render workspace validation returned only `need_payment_info` for each paid resource; add a valid client-owned payment method and repeat validation immediately before sync.
- Cloudinary write, HTTPS delivery and deletion were verified with a synthetic image on 2026-07-28. Persistence across a Render redeploy still requires funded staging evidence; staging and production now fail closed without Cloudinary credentials.
- The final Items 11–15 batch passes the complete local test suite, but GitHub
  Actions cannot be marked green until that batch is committed and pushed.
- Daraja and notification providers are verified through mocks/local controls, not complete provider certification.
- Customer restock requests are implemented and locally verified, but actual SMS delivery remains subject to the same Africa's Talking staging/production certification. The alert reports observed availability and never guarantees or reserves stock.
- Scheduled-report email is locally failure-safe and configured for Brevo SMTP, but remains disabled until the business domain/sender and staging provider delivery are manually verified.
- Customer order and verification-code email is implemented with durable delivery evidence but remains safely suppressed until the same client-owned sender and SMTP credentials pass staging certification.
- A local PostgreSQL custom-format archive has been restored successfully into an
  isolated database with matching core counts. Managed-host PITR and off-site
  encrypted-archive restore remain unverified until staging is funded.
- Monitoring endpoints and the Beat-to-worker heartbeat are implemented locally, but no external uptime, Render or Sentry alert/recovery delivery has been proven because staging is unfunded.
- The load tool is locally verified, but production-sized staging load, an approved peak-workload model and an independent penetration test/retest are outstanding launch gates.
- The current working tree's **718-test** SQLite regression passes with one
  expected skip because SQLite does not expose `select_for_update`. The 72 focused
  catalogue, stock-presentation, destination and delivery-quote tests pass on
  PostgreSQL. The repeatable full PostgreSQL verification now passes all 718
  tests with zero skips, and the focused critical-flow run passes 31 tests; the
  committed staging release must repeat the suite through PostgreSQL-backed CI.
  Production-sized load, Nairobi-to-Frankfurt latency, external security and
  client UAT remain pending.

## Business configuration

- The four `DEMO-` catalogue products and their quantities are visual/staging fixtures, not client-approved production merchandise. Production launch requires the client-provided catalogue, images, prices, variant matrix and counted opening stock; do not run `seed_demo_catalog` in production.
- The approved OTC Mall, Gaberone Plaza S18 and Gaberone Plaza B03 records are reproducibly configured by `configure_business_branches`; the command still needs to be run after migrations when each external environment is provisioned.
- Real staff assignments, opening stock and pickup arrangements require controlled environment-specific onboarding and must not be invented by a seed command.
- Town-parcel quote requests and acceptance are implemented, but the client must approve the real staff rota, supported parcel restrictions, loss/damage wording and operator-selection procedure. Fares are deliberately entered by authorized staff after route verification; no invented static route table is published.
- Quote working hours are Monday-Saturday, 8:00 AM-6:00 PM Africa/Nairobi. Closure/public-holiday dates can be configured in administration, but the client must maintain that calendar.
- WhatsApp assists conversation only; it does not reserve stock or verify payment.

## Financial and returns boundaries

- Automated M-Pesa refunds are not implemented. Approved return refunds are tracked for manual reconciliation.
- Partial/over payments and unidentified callbacks enter reconciliation rather than ordinary success.
- Exact order-total equality and order-item multiplication are enforced by services/tests, not complete database expressions.
- Customer-entered Paybill/reference values never prove payment.
- Automatic walk-in C2B matching is deferred by client decision. Launch uses audited manager verification; amount-and-time-only matching is prohibited. Future C2B work requires a client-controlled enabled shortcode, unique order reference and provider certification.

## Data/security design debt

- `StockAuditLog` and `OrderStatusHistory` are append-only by service convention/permissions, not database-trigger immutability.
- Category cycles, some promotion rules and product non-negative price rely on application validation rather than complete DB constraints.
- Authorization permission classes are duplicated across apps; behavior is tested but not yet centralized.
- API documentation is Markdown; no published, versioned OpenAPI compatibility contract exists.
- Legal compliance and security certification cannot be claimed from code review.
- The ordinary local `.env` still selects SQLite for lightweight development.
  Release evidence uses the protected repeatable PostgreSQL mode in
  `start_local_postgres.ps1 -VerifyRelease`; repeat it on the exact committed SHA.
- Production backup settings fail closed when disabled, but a true scheduled job
  is not currently declared in Celery Beat or the production Blueprint. Paid
  Render PITR plus a separate version-compatible Render-to-S3 Cron Job must be
  provisioned, triggered and restored before launch; `BACKUP_ENABLED=True` alone
  is not backup evidence.
- Production can currently boot without a Sentry DSN. Monitoring is therefore an
  external launch gate until the client-owned project and alert path are active.

## Operational/UI boundaries

- Barcode scanners, receipt printers, fiscal/tax devices and offline POS are not certified.
- Bulk catalog/inventory import/export is not implemented because no format/workflow is approved.
- Route optimization, public live rider maps and native mobile apps are absent.
- Image search is deferred; text/category/filters and WhatsApp assistance remain discovery paths.
- Preorders and backorders remain deliberately disabled. Restock alerts are informational only and cannot create negative or reserved inventory.
