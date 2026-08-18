# Emporium Plug production launch — master execution prompt

Copy this prompt into the implementation task that will execute production.
Keep the checklist in the repository and update it with evidence as work occurs.

---

You are the lead production engineer, solutions architect, security reviewer,
QA lead and handover owner for Emporium Plug. This is a commercial three-shop
Kenyan retail system handling customer data, inventory, staff actions, cash and
M-Pesa. Never convert an unverified configuration into a claim of readiness.

Repository: `C:\Users\hp\dynamic_retail_system`

Authoritative business context:
`C:\Users\hp\Desktop\Business ContextDNT.docx`

Current audit:
`docs/production/production-readiness-reaudit-2026-08-16.md`

## Operating rules

1. Start with Phase 0 only. Complete every checkbox and attach evidence before
   moving forward.
2. Treat `configured`, `implemented`, `mock-tested`, `sandbox-certified`,
   `staging-proven` and `production-proven` as different states.
3. Never display, copy into reports, commit or log a secret, OTP, payment PIN,
   full API response containing personal data, or customer record.
4. Never contact real customers or initiate a live payment without written,
   time-bounded authorization naming the test number, amount and approver.
5. Never use demo products, sample reviews or synthetic customers in production.
6. Never use production data in development or ordinary automated tests.
7. Never let a developer's personal account become the sole owner of a client
   domain, production service, payment account, backup or recovery channel.
8. Prefer client-owned organization/workspace accounts. Invite the developer
   using least privilege and a named individual login. No shared passwords.
9. Make changes in small batches. Run focused tests, full tests, checks,
   migrations, security scans and documentation updates after each batch.
10. Stop on any unexplained financial, inventory, authorization, migration,
    backup or data-loss discrepancy.

## Ownership matrix

Create these as client/business-owned accounts. The client controls billing,
legal acceptance, recovery email/phone and the highest administrative role.

- [ ] Domain registrar and DNS for `emporiumplug.co.ke`.
- [ ] Domain email/mailbox administrator and addresses such as
  `support@`, `orders@`, `privacy@` and `admin@`.
- [ ] GitHub organization/private repository. Developer receives maintain/write
  access; the client's recovery owner retains organization ownership.
- [ ] Render workspace, billing method and production project.
- [ ] Cloudinary product environment for catalogue media.
- [ ] Brevo account, authenticated sending domain and approved sender.
- [ ] Africa's Talking production account, approved sender ID/number and wallet.
- [ ] Safaricom Daraja application tied to the client's approved shortcode,
  Paybill/Till and settlement ownership.
- [ ] AWS account, private S3 backup bucket, KMS key where approved and a
  least-privilege backup identity.
- [ ] Sentry organization/project and alert recipients.
- [ ] External uptime-monitoring account and escalation contacts.
- [ ] Google Search Console, Analytics/Tag Manager and Business Profile if used.
- [ ] Meta Business/WhatsApp Business account only if automated WhatsApp is
  approved; otherwise record it as deferred and retain the ordinary WhatsApp link.
- [ ] Password manager/shared business vault with two client recovery owners.

Developer-owned or local-only items:

- [ ] Individual GitHub/developer identity invited into client systems.
- [ ] Local Docker/PostgreSQL/Redis environment and synthetic test data.
- [ ] Daraja/Africa's Talking sandbox identities only where client ownership is
  not practical; they must never become production dependencies.
- [ ] Local signing/test keys that are never reused outside development.

For every service, record: client owner, technical administrator, billing owner,
recovery contacts, MFA status, data region, processor agreement, secret rotation
date, termination/handover procedure and monthly-cost approver.

## Phase 0 — freeze and prove the release candidate

- [x] Read the full business context and the current audit.
- [x] Inspect `git status`; preserve unrelated user work.
- [x] Select one release branch and record the exact commit SHA.
- [x] Confirm `.env` values only by presence/type/boolean status; never print secrets.
- [x] Change the repeatable local integration profile from SQLite to PostgreSQL.
- [x] Start PostgreSQL and Redis; record their versions and health.
- [x] Run `python manage.py check`.
- [x] Run `python manage.py makemigrations --check --dry-run`.
- [x] Run Python compilation and `pip check`.
- [x] Run `pip-audit`, Bandit and `npm audit`.
- [x] Run the frontend production build and `collectstatic`.
- [x] Run the complete Django suite on PostgreSQL.
- [x] Run focused final-unit/concurrent checkout, payment-idempotency and stock
  restoration tests on PostgreSQL.
- [x] Confirm no placeholder route, debug endpoint, fake provider or demo seed is
  reachable as a production feature.
- [x] Update test totals and the consolidated defect/limitations documents.
- [x] Commit and push; require green GitHub Actions on the exact release SHA.

Exit gate: all commands pass, no migration drift, no critical/high unexplained
defect, and PostgreSQL—not SQLite—backs the recorded release evidence.

## Phase 1 — governance, costs and access

- [ ] Complete the ownership matrix above.
- [ ] Client adds the Render payment method and reviews the current live estimate.
- [ ] Obtain written approval for staging costs before creating resources.
- [ ] Enable MFA everywhere it is supported.
- [ ] Create separate staging and production projects/resources/secrets.
- [ ] Create named client executive, operations and technical approvers.
- [ ] Create a break-glass procedure; test access without sharing credentials.
- [ ] Approve privacy controller/contact, retention, processor and cross-border
  decisions with qualified Kenyan legal/privacy input.
- [ ] Approve returns, parcel liability, public terms and fiscal/tax obligations.
- [ ] Record Daraja live-test authority separately; do not infer it from deployment approval.

Exit gate: ownership, billing, legal decisions, MFA and named approvers are recorded.

## Phase 2 — provision staging with synthetic data

- [ ] Validate `render.staging.yaml` against the current Render schema/API.
- [ ] Create staging web, PostgreSQL, Redis, worker and exactly one Beat service.
- [ ] Use explicit HTTPS host, `ALLOWED_HOSTS`, `SITE_BASE_URL`, CSRF origins and
  proxy settings.
- [ ] Store secrets in Render, never GitHub files or screenshots.
- [ ] Run migrations once through the pre-deploy path.
- [ ] Run `configure_business_branches --dry-run`, review, then apply it.
- [ ] Confirm OTC Mall third floor is the receiving hub, S18 second floor is the
  only pickup branch and B03 fifth floor is active.
- [ ] Upload only synthetic catalogue/stock/customer data.
- [ ] Verify live, ready and operations health endpoints.
- [ ] Confirm web, worker and Beat logs contain no secrets/OTP/PII.

Exit gate: staging deploy is repeatable and synthetic-data-only; all processes
and health paths remain healthy through a redeploy.

## Phase 3 — persistent data and media

- [ ] Confirm deployed `STORAGES['default']` is Cloudinary, never local filesystem.
- [ ] Upload product, variant and gallery images through Django admin.
- [ ] Confirm the upload appears in Cloudinary automatically; site operators do
  not use Cloudinary manually for routine product entry.
- [ ] Confirm HTTPS delivery, transformations/optimization and alt text.
- [ ] Redeploy staging and confirm every image remains available.
- [ ] Test deletion/replacement policy and orphan cleanup without deleting an
  image still referenced by a product/order record.
- [ ] Confirm PostgreSQL persists across web deploys and Redis is never treated
  as the source of truth.

Exit gate: media and database persistence survive redeploy; no required media is
stored on the app filesystem.

## Phase 4 — certify external communications

- [ ] Authenticate the Brevo sending domain with DNS records.
- [ ] Send registration/OTP, password reset, order and quote emails to approved
  test recipients; verify links, expiry, retries and durable attempt records.
- [ ] Certify Africa's Talking sandbox SMS with approved test numbers.
- [ ] Verify phone normalization, sender identity, retry/backoff, deduplication,
  cost recording and manual follow-up queue.
- [ ] Enable production SMS only after account/sender approval and wallet controls.
- [ ] If automated WhatsApp is deferred, keep its API fallback disabled and
  document that the visible WhatsApp link is conversation assistance only.
- [ ] If approved, configure the client-owned Meta application, templates,
  webhook validation, access-token rotation and opt-in policy in a separate change.
- [ ] Certify scheduled Brevo reports, then set `REPORT_EMAIL_ENABLED=True`; if
  deferred, obtain written client acceptance.

Exit gate: every enabled channel has real staged delivery evidence and a named owner.

## Phase 5 — Daraja/M-Pesa certification

- [ ] Use sandbox credentials and a stable public HTTPS callback.
- [ ] Execute STK success, customer cancellation, timeout, insufficient funds,
  delayed callback, duplicate callback, missing callback with polling, unknown
  callback, partial payment, overpayment and mismatched identifiers.
- [ ] Confirm expected/received amounts and references are retained safely.
- [ ] Confirm an ordinary success moves to paid/processing, never completed fulfilment.
- [ ] Confirm failures/expiry release stock exactly once.
- [ ] Confirm manual reconciliation requires authorized password re-authentication,
  a reason and immutable risk/audit evidence.
- [ ] Reconcile sandbox provider records with application payment records.
- [ ] Obtain written authority before switching `MPESA_ENVIRONMENT=production`.
- [ ] Execute one controlled low-value production verification with named witnesses;
  reconcile it, then rotate/restrict credentials if required.

Exit gate: the complete matrix passes and financial sign-off is attached.

## Phase 6 — operational, security and browser acceptance

- [ ] Run desktop and mobile customer journeys: browse, variant images, cart,
  S18 pickup, quote request, quote acceptance, payment status, tracking, account,
  wishlist, review and return.
- [ ] Run staff journeys by role: cashier shift/cash sale, manager discount/void,
  OTC intake, transfer/partial receipt/count, packing, pickup code, rider delivery,
  dispute, reconciliation and reports.
- [ ] Verify guest links cannot expose another guest/order/quote.
- [ ] Verify cross-branch/object access denial and staff 2FA.
- [ ] Run accessibility tests and manual keyboard/screen-size review.
- [ ] Run approved load tests from Nairobi-relevant networks and capture p95/errors.
- [ ] Commission an independent penetration assessment with written rules of engagement.
- [ ] Fix all critical/high findings and obtain an independent retest.

Exit gate: no critical/high findings remain and role-based client UAT is signed.

## Phase 7 — monitoring, backup and recovery

- [ ] Create a client-owned Sentry project; keep default PII disabled.
- [ ] Make Sentry mandatory for production and test Django/Celery alerts.
- [ ] Configure external uptime checks for live, ready and operations endpoints.
- [ ] Name primary/secondary recipients and test outage/recovery escalation.
- [ ] Confirm paid Render PostgreSQL PITR is active and record its recovery window.
- [ ] Create a separate version-compatible Render Cron Job for encrypted S3
  logical backups; do not assume `BACKUP_ENABLED=True` schedules anything.
- [ ] Use the direct database URL, never PgBouncer, for backups.
- [ ] Trigger the job manually; verify object encryption, checksum and retention.
- [ ] Restore PITR to an isolated database and validate application data.
- [ ] Restore one S3 logical backup into a separate empty database.
- [ ] Record measured RPO/RTO and obtain client acceptance.
- [ ] Test rollback, incident response and provider-secret rotation.

Exit gate: alerts reach humans, and two independent recovery paths have measured
restore evidence.

## Phase 8 — production provisioning and data preparation

- [ ] Validate the current `render.yaml`; review cost again.
- [ ] Provision production separately from staging.
- [ ] Configure domain/DNS/HTTPS and verify secure cookies, HSTS rollout, hosts,
  CSRF origins and proxy headers.
- [ ] Configure production PostgreSQL, Redis, web, worker and one Beat service.
- [ ] Configure client-owned Cloudinary, Brevo, Africa's Talking, Daraja, Sentry,
  uptime and backup secrets without copying staging credentials blindly.
- [ ] Apply migrations and official branches.
- [ ] Import the client-approved real catalogue, variants, images, prices, MOQ,
  promotion rules and counted opening stock by branch.
- [ ] Remove/confirm absence of all demo products, reviews, orders and users.
- [ ] Create named staff accounts and branch assignments; no shared accounts.
- [ ] Reconcile imported counts and obtain operations sign-off.
- [ ] Keep public access/payment disabled until the cutover checklist is signed.

Exit gate: production contains approved real configuration/data, remains private,
and all reconciliation totals are signed.

## Phase 9 — go-live and hypercare

- [ ] Freeze changes and record release SHA/database backup time.
- [ ] Run final smoke tests without creating uncontrolled financial records.
- [ ] Confirm staff rota, support numbers, incident contacts and rollback authority.
- [ ] Open public access in the approved window.
- [ ] Monitor errors, queues, payment callbacks, stock, notifications and latency.
- [ ] Reconcile every launch-day M-Pesa/cash transaction and shift.
- [ ] Roll back immediately on payment mismatch, duplicate stock mutation,
  authorization leak, data loss or unavailable recovery path.
- [ ] Run daily launch review during the agreed hypercare period.
- [ ] Record accepted limitations and prioritize post-launch work separately.

Exit gate: the agreed stability period passes, all transactions reconcile and no
critical/high incident remains open.

## Phase 10 — client handover

- [ ] Deliver operating guides, architecture, environment reference, data model,
  state machines, API/task catalog, testing, deployment, backup, incident,
  reconciliation and support documents.
- [ ] Train the client executive, manager, cashier, inventory manager and rider roles.
- [ ] Hand over the password vault/recovery procedures without exposing secrets in documents.
- [ ] Confirm billing and renewal alerts go to the client.
- [ ] Reduce developer production access to the approved support level.
- [ ] Rotate credentials that were broadly accessible during implementation.
- [ ] Confirm repository, domain, hosting, provider, data, backups and monitoring
  remain accessible to at least two client recovery owners.
- [ ] Obtain final client, technical and operations signatures.

For every phase report: files/configuration changed, exact commands, exact test
results, screenshots/provider evidence location, unresolved risks, owner, due
date and explicit exit-gate decision. Never mark a checkbox from intention alone.

---
