# Client MVP release checklist

No one may approve release while an unchecked launch blocker remains. Attach evidence and named approver.

## Code and data

- [ ] Release revision identified; CI and full suite pass.
- [ ] Checks, migration drift, compilation, dependency consistency and frontend build pass.
- [ ] PostgreSQL migrations reviewed for locks/runtime/rollback.
- [ ] `configure_business_branches --dry-run` reviewed, then official OTC Mall, S18 and B03 records/addresses/capabilities applied and inspected.
- [ ] Staff roles/branches verified; no shared accounts.
- [ ] PostgreSQL concurrency and production-sized staging load tests pass.
- [ ] Independent penetration assessment findings are resolved and independently retested under approved rules of engagement.

## Critical journeys

- [ ] Guest/customer S18 pickup passes with the selected pickup method, active arrangement, exact total, confirmation, code and expiry.
- [ ] “Send to my town” opens the approved cart-aware WhatsApp conversation without creating an order, reserving stock or presenting an invented transport fee.
- [ ] M-Pesa success, duplicate, missing callback/poll, cancellation, timeout, partial, excess and unknown cases pass in sandbox.
- [ ] Failed/expired payments and pickups restore stock once.
- [ ] Walk-in cash sale, receipt, shift close, discount and void pass.
- [ ] OTC intake and OTC→Gaberone transfer/partial receipt/count pass.
- [ ] Packing, rider delivery/confirmation/dispute and eligible return pass.
- [ ] Reports reconcile to source transactions.

## Production engineering

- [ ] **Funding reminder:** add a valid client-owned Render payment method, review the live monthly Blueprint estimate, and obtain approval before creating billable resources (deferred 2026-07-28).
- [ ] Separate staging/production DB, Redis, provider, storage, Sentry and secrets exist.
- [ ] HTTPS/domain, cookies, hosts/origins and proxy verified.
- [ ] Web, worker and exactly one Beat process healthy; alerts tested.
- [ ] `/health/live/`, `/health/ready/` and `/health/operations/` failure and recovery drills have timestamped evidence and named recipients.
- [ ] Persistent media verified across deploys.
- [ ] Managed PITR enabled; off-site backup policy configured if approved.
- [ ] Uploaded logical archive passes `verify_database_backup` before restore testing.
- [ ] Controlled restore succeeds; RPO/RTO measured and accepted.
- [ ] Deployment and rollback rehearsed; incident contacts filled.

## Security, privacy and providers

- [ ] External security/accessibility high/critical findings closed.
- [ ] Controller/contact, notice, retention, processor/cross-border decisions approved.
- [ ] Sentry/logs/provider payloads checked for PII/secrets.
- [ ] Daraja sandbox certified; production activation explicitly authorized.
- [ ] Notification provider, sender/number, purpose and fallback policy accepted.
- [ ] Public returns, pickup, delivery and terms wording approved.

## Acceptance

- [ ] Client UAT signed for customer, cashier, inventory, manager and rider journeys.
- [ ] Known limitations/deferred features accepted in writing.
- [ ] Support staff trained; reconciliation/backup/incident owners named.
- [ ] Launch window, rollback authority, communications and monitoring staffed.

Final approval: client executive ___ technical lead ___ operations lead ___ date/time ___ release ___
