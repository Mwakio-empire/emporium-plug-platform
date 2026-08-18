# Pre-production hardening programme

This register separates work that can be completed in source control from work
that requires funded infrastructure, provider access, client decisions or manual
evidence. No external gate may be converted into a pass from mocks or code review.

## Completed in the current working tree

- [x] Stable lock ordering for two-branch transfer receipts.
- [x] Delivery leases for SMS and transactional email, including unknown-outcome
  manual reconciliation instead of blind resend.
- [x] Production startup rejects Daraja sandbox mode and incomplete credentials.
- [x] Production startup requires certified transactional email configuration.
- [x] Production startup requires an enabled encrypted off-site backup job.
- [x] Production Blueprint requests live M-Pesa mode, Brevo delivery and backup secrets.
- [x] Private utility pages emit `noindex,nofollow`.
- [x] Migration `notifications.0004` created and applied locally.
- [x] Full local SQLite regression passes: 710 tests, one expected row-lock skip.
- [x] Full local PostgreSQL regression passes: 710 tests, zero skipped and zero failed.
- [x] PostgreSQL-only nullable-join locking defects in restock alerts and delivery
  quote acceptance are corrected and regression tested.
- [x] Desktop and 390×844 mobile browser smoke QA passes for storefront search,
  checkout privacy/layout and sign-in password visibility, with no console errors.
- [x] Current Python and production JavaScript advisory scans report no known vulnerabilities.

## Source-control release work

- [ ] Review the complete dirty working tree and split unrelated/user work only
  where ownership is clear.
- [ ] Confirm no secrets, local databases, media or backup archives are tracked.
- [ ] Commit the reviewed migration and implementation as one identifiable release.
- [ ] Push the release and obtain green GitHub Actions for that exact commit.
- [ ] Record the commit SHA in the release checklist and Sentry release configuration.

## Funded staging certification

- [ ] Add the client-owned Render payment method and approve the live estimate.
- [ ] Provision staging web, PostgreSQL, Redis, worker and exactly one Beat service.
- [ ] Supply separate staging Cloudinary, Daraja sandbox and provider credentials.
- [ ] Run migrations and `configure_business_branches --dry-run`, then apply it.
- [x] Run the current working tree's full suite against local PostgreSQL,
  including row-lock concurrency tests. Repeat against the committed staging release.
- [ ] Verify health failure/recovery for database, Redis, worker and Beat.
- [ ] Run the complete authenticated role-by-role browser/UAT pack and automated
  accessibility checks against the exact staging release.
- [ ] Run the approved catalog/checkout/callback load model and record p95/error rate.

## Provider certification

- [ ] Complete Daraja sandbox cases: success, cancellation, timeout, delayed or
  missing callback, query success, duplicate, unknown, partial and excess payment.
- [ ] Verify Brevo sender/domain and synthetic delivery without exposing codes.
- [ ] Verify Africa's Talking production account/sender and controlled synthetic SMS.
- [ ] Confirm callbacks, logs and Sentry contain no OTP, secret or unnecessary PII.
- [ ] Perform one authorized low-value production payment only after written approval.

## Recovery and operations

- [ ] Confirm managed PostgreSQL PITR retention for the purchased plan.
- [ ] Configure the least-privilege encrypted backup bucket and lifecycle.
- [ ] Upload, verify and restore a production-format archive into an isolated database.
- [ ] Measure RPO/RTO and obtain client acceptance.
- [ ] Test Sentry, uptime and worker alerts through failure and recovery.
- [ ] Rehearse deployment rollback and payment/notification incident response.

## Client launch gates

- [ ] Import approved products, images, variants, prices and counted opening stock.
- [ ] Create named staff accounts with approved roles and branches; no shared accounts.
- [ ] Approve privacy controller/contact, retention, processors and public policies.
- [ ] Approve parcel restrictions, operator procedure and loss/damage wording.
- [ ] Complete customer, cashier, inventory, manager and fulfilment UAT.
- [ ] Train owners for shifts, reconciliation, fulfilment, backups and incidents.
- [ ] Sign the known limitations and production activation decision.
