# Production-readiness re-audit — 16 August 2026

## Scope and evidence

This audit compares the current repository with `Business ContextDNT.docx` and
the current three-shop operating decisions. It distinguishes locally executable
evidence from provider, hosted-environment and client-acceptance evidence.

Evidence executed for this audit:

- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- Python compilation: passed.
- `pip check`: passed.
- `pip-audit`: no known Python dependency vulnerabilities.
- `npm audit --omit=dev --audit-level=moderate`: no known production JavaScript
  dependency vulnerabilities.
- Frontend production build: passed; Browserslist data-age warning remains.
- Complete Django suite after the storage and production demo-data corrections:
  718 passed, one expected
  SQLite row-lock skip.
- Repeatable PostgreSQL release verification: 718 passed with zero skips after
  migrations, checks, drift and compilation passed.
- Focused PostgreSQL release verification: 31 final-unit locking,
  payment-idempotency/polling and stock-restoration tests passed.
- Branch dry run: OTC Mall third floor is the intake hub; S18 second floor is
  the only customer pickup shop; B03 fifth floor is active without pickup.
- Current local runtime: development, SQLite, Redis, Cloudinary catalog URLs,
  Brevo SMTP enabled, Africa's Talking sandbox, Daraja sandbox, backups off,
  Sentry off and WhatsApp API fallback off.

Negative-path warnings written during the test suite are expected assertions,
not production incidents. Provider mocks are not provider certification.

## Honest readiness score

There is no honest basis for calling this project 95–100% production-ready yet.

| Area | Local implementation | Production proof | Main gap |
|---|---:|---:|---|
| Baseline, migrations and CI | 99% | 75% | PostgreSQL-backed CI is configured; latest release is not yet pushed through green CI. |
| Domain, inventory and branch isolation | 94% | 60% | PostgreSQL passes locally; hosted load/concurrency proof remains. |
| Authentication and account flows | 91% | 55% | Real email/SMS delivery and staff UAT are outstanding. |
| Storefront, catalogue and cart | 93% | 55% | Demo catalogue must be replaced and browser/UAT evidence repeated. |
| Checkout and order access | 91% | 50% | Hosted guest/pickup/quote journeys are unverified. |
| M-Pesa and financial reconciliation | 82% | 25% | Daraja sandbox certification and authorized production verification are missing. |
| POS, inventory and fulfilment | 89% | 45% | Cashier, manager, inventory and rider UAT are missing. |
| Reports and notifications | 84% | 35% | Report email is disabled; providers are not certified. |
| Security and privacy | 82% | 35% | External assessment and approved Kenyan privacy decisions are missing. |
| Production engineering and recovery | 67% | 20% | No funded staging, active Sentry/uptime alerts, proven backup schedule or hosted restore. |
| Documentation and handover | 84% | 45% | Several current-status documents are stale and owners/signatures are absent. |

Weighted view: approximately **89% locally implemented**, **60% launch-ready**,
and **under 40% externally proven**. These are engineering estimates, not a
certification. The score must rise through evidence, not by changing labels.

## Requirements traceability summary

| Capability | State | Evidence | Remaining gate |
|---|---|---|---|
| Healthy baseline | Complete and verified locally | Checks, drift, compilation and 718-test pass | Commit, push and green CI on the release revision |
| Three-branch topology | Complete and verified locally | Idempotent branch command and dry run | Apply and inspect in staging/production |
| Catalog images | Corrected locally | Catalog fields use Cloudinary; deployed default media now selects Cloudinary | Focused/full regression, hosted upload and redeploy persistence test |
| PostgreSQL | Complete and verified locally | `start_local_postgres.ps1 -VerifyRelease`; 718 tests, zero skips; 31 focused critical-flow tests | Repeat on committed SHA and production-sized staging |
| Redis/Celery | Implemented and locally configured | Redis cache/broker and Beat schedules | Hosted web/worker/Beat heartbeat and failure drill |
| Brevo email | Implemented but externally unverified | SMTP backend and durable email attempts | Domain/sender verification and staged delivery evidence |
| Africa's Talking SMS | Implemented but externally unverified | Durable attempts/retries; sandbox configuration | Sandbox delivery, sender approval and production account |
| M-Pesa | Implemented but externally unverified | STK/callback/polling/idempotency/reconciliation tests | Daraja certification; controlled production test only after approval |
| WhatsApp | Partial/deferred | Assisted-order link and optional API adapter | Client-owned Meta/WhatsApp approval if automated fallback is required |
| Backups | Partially implemented | Native dump/upload/verify code and local restore history | One scheduled production mechanism, compatible client tools, PITR and measured restore |
| Monitoring | Partially implemented | Health endpoints, heartbeat and optional Sentry config | Required Sentry project, uptime monitor, named alerts and recovery drill |
| Security/privacy | Implemented but externally unverified | Local review, controls and runbooks | Legal approval, external test and processor/retention decisions |
| Client operations | Implemented but unverified | POS/inventory/fulfilment/report interfaces | Role-based client UAT and signed acceptance |

## Prioritized defect and gate register

### P0/P1 — must be resolved before a release candidate is promoted

| ID | Severity | Finding | Business/security impact | Resolution/evidence required |
|---|---|---|---|---|
| REL-001 | High | Corrected: ordinary `.env` still permits lightweight SQLite development, but release verification previously depended on temporary shell state. | SQLite does not prove row locks or production concurrency and can hide environment drift. | Added a protected repeatable PostgreSQL verification mode; 718 tests pass with zero skips. Repeat on the committed SHA. |
| REL-002 | High | Deployed Django default media storage previously remained local even though catalog fields used Cloudinary. | Future ordinary uploads could disappear on a redeploy. | Corrected in the working tree; tests now require deployed Cloudinary default storage. Complete regression and hosted persistence proof remain. |
| REL-003 | High | Bandit's CI command reported two medium findings. | GitHub CI would fail; an unreviewed suppression would weaken assurance. | Corrected narrowly: validation text no longer triggers SQL heuristics; fixed provider URL has an explained `B310` exception. Re-run CI. |
| REL-004 | High | Corrected locally: the SQLite pass has one expected row-lock skip. | Final-unit sales and lock behavior require PostgreSQL evidence. | The repeatable PostgreSQL run passes all 718 tests with zero skips and the focused critical-flow run passes 31; commit/CI and hosted load evidence remain. |
| REL-005 | High | Current handover records contain stale test counts and already-resolved branch/location decisions. | Client or operator could follow incorrect release information. | Refresh Phase 13–15 traceability, limitations, verification and release documents from this audit. |
| REL-006 | High | Corrected locally: GitHub Actions used SQLite even though release evidence requires PostgreSQL. | CI could miss row-lock/concurrency failures on the exact release commit. | CI now provisions PostgreSQL 17 and Redis 7 and uses PostgreSQL for Django checks/tests; obtain a green run on the pushed release SHA. |
| REL-007 | High | Corrected locally: the demo-review command was production-blocked but the demo-catalogue command was not. | An operator could accidentally create synthetic products/stock in production. | The catalogue seed now fails before mutation when `IS_PRODUCTION=True`; regression coverage passes. |
| REL-008 | High | The first pushed CI run identified four 2026 vulnerabilities in `sqlparse==0.5.5`. | Retaining the vulnerable parser would fail the security gate and expose avoidable dependency risk. | Upgraded to fixed `sqlparse==0.6.0`; local audit is clean and the full 718-test PostgreSQL regression passes. A green exact-SHA CI rerun remains required. |

### Production engineering blockers

| ID | Severity | Finding | Business/security impact | Resolution/evidence required |
|---|---|---|---|---|
| PROD-101 | Critical | Render resources are not provisioned because the client-owned account has no funded payment method. | There is no staging or production system to certify. | Client adds billing, approves estimate and provisions staging first. |
| PROD-102 | Critical | `BACKUP_ENABLED=True` is a boot gate, but neither Celery Beat nor `render.yaml` schedules the backup task. | Operators could believe backups exist when none are running. | Use paid Render PITR plus one explicit Render backup Cron Job to encrypted S3; trigger, verify and restore it. Do not rely on the flag. |
| PROD-103 | High | The application dump code calls `pg_dump` while production PostgreSQL is declared as major 17. A compatible client version is not proven for the native worker. | Backup jobs can fail with a server/client version mismatch. | Use Render's version-aware backup Cron pattern or pin a compatible runtime; prove the exact command against staging. |
| PROD-104 | High | Production can boot with an empty Sentry DSN. | Critical payment/order failures may have no operational alert. | Create a client-owned Sentry project, keep PII off, fail closed in production and test an alert/recovery path. |
| PROD-105 | High | No external uptime monitor or named recipient is active. | Outage detection depends on a person noticing. | Create client-owned monitoring, exercise live/readiness/operations failures and retain timestamps. |
| PROD-106 | High | Production report email is explicitly disabled. | Required scheduled management summaries will not be delivered. | Certify Brevo then enable, or obtain a signed MVP deferral while in-app/export reports remain available. |

### Provider, data and acceptance blockers

| ID | Severity | Finding | Resolution/evidence required |
|---|---|---|---|
| EXT-201 | Critical | Daraja code is mock-tested but not sandbox-certified. | Execute the written sandbox matrix; never run a live charge without written authority. |
| EXT-202 | High | Brevo and Africa's Talking settings exist but real delivery is unproven. | Verify sender/domain/number, send only to approved test recipients and retain provider evidence. |
| EXT-203 | High | The database contains demo products/reviews and no approved production catalogue/opening stock. | Export/approve client data, import it into staging, count stock by branch and never seed demos in production. |
| EXT-204 | High | Privacy notice/controller/retention/processor decisions lack final client/legal approval. | Complete the decision register before collecting real customer data. |
| EXT-205 | High | External penetration/accessibility assessment and client UAT are absent. | Test staging, fix all critical/high findings, retest and sign UAT by role. |
| EXT-206 | Medium | Automated WhatsApp fallback is disabled and unconfigured. | Keep it explicitly deferred or provision a client-owned Meta channel and templates. |

## Corrected phase order

1. Freeze and verify the release candidate on PostgreSQL.
2. Correct configuration truthfulness and current documentation.
3. Establish client-owned accounts, billing, recovery and access roles.
4. Provision synthetic-data staging only.
5. Certify media, email, SMS, M-Pesa and monitoring independently.
6. Prove PostgreSQL concurrency, backup/restore, load and security.
7. Run client UAT with the approved real catalogue but non-live payments where possible.
8. Provision production with separate secrets/data/providers.
9. Execute a controlled cutover and low-value payment verification with written authority.
10. Complete handover, revoke excess developer access and enter monitored hypercare.

No later phase may be marked complete while a critical/high exit gate in the
current phase remains open.
