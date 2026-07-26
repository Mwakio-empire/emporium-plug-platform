# Phase 0: Baseline Audit and Stabilization

Date: 2026-07-21  
Status: active; startup baseline restored

## Executive assessment

The repository contains substantial domain and test coverage, but the original baseline could not import Django. Phase 0 restored startup, enabled the complete test suite, repaired routing placeholders, reconciled migrations, isolated test infrastructure, and corrected critical M-Pesa settlement behaviour.

This document distinguishes verified behaviour from intended future scope. It does not certify production readiness.

## Evidence collected

- Django applications: branches, users, catalog, inventory, orders, payments, notifications, logistics, analytics, reports, marketing, and core.
- Initial `manage.py check`: failed during `users.models` import.
- Initial full test attempt: could not execute because Django could not start.
- After startup repairs: 202 tests executed; two errors identified the disconnected M-Pesa callback route.
- Current automated baseline after the first Phase 0 batches: 206 tests passing.
- `manage.py check`: passing.
- `makemigrations --check --dry-run`: passing after two missing choice-field migrations were generated.
- Python compilation: passing.
- `pip check`: passing.
- Dependency vulnerability scanning: not executed because a vulnerability-audit tool is not installed in the current environment.
- Live Daraja, SMS, WhatsApp, storage, deployment, backup and restore behaviour: not verified and must not be represented as production-ready.

## Requirements traceability matrix

| Capability | Current state | Evidence/limitation | Next owning phase |
|---|---|---|---|
| Roles and branch scoping | Partially implemented | Models, permission checks and tests exist; full permission matrix still required | Phase 1-2 |
| Customer registration/login | Complete and tested at API level | HTML OTP and reset flows need expanded security regression coverage | Phase 2 |
| Staff 2FA | Implemented but not fully verified | OTP services and views exist | Phase 2 |
| Branch listing | Complete and verified | Active branches exposed by a real read-only endpoint | Phase 0 |
| Branch administration | Model only/admin dependent | No dedicated client operations UI | Phase 7/client operations |
| Product catalog and variants | Partially implemented and tested | Single product image; advanced media/SEO/bulk tooling absent | Phase 3 |
| Customer cart | Implemented and tested | Session-based; post-login merge not verified | Phase 3 |
| Authenticated checkout page | Implemented and minimally tested | Uses existing delivery/pickup/payment APIs | Phase 0/4 |
| Guest checkout | Missing | Business requirement; requires secure guest tracking token | Phase 4 |
| POS sales | Implemented and tested | Hardware/customer-facing secondary display unverified | Phase 6 |
| Inventory adjustment/audit | Implemented and tested | Rich inventory states and cycle counts absent | Phase 1/7 |
| Inter-branch transfer | Partially implemented and tested | Dispatch/in-transit/partial receipt model incomplete | Phase 7 |
| M-Pesa STK initiation | Implemented with mocked tests | Sandbox certification not performed | Phase 5 |
| M-Pesa callback | Implemented and tested | Route connected; amount validation and idempotent settlement verified in unit/integration tests | Phase 0/5 |
| Payment polling | Implemented and tested | Provider sandbox behaviour unverified | Phase 5 |
| Cash reconciliation | Partially implemented and tested | Operational acceptance with client required | Phase 6/10 |
| Delivery and pickup | Partially implemented and tested | Packing workflow and full customer UI incomplete | Phase 8 |
| Notifications | Partially implemented and mocked | Durable notification ledger/deduplication absent | Phase 11 |
| Promotions | Partially implemented and tested | Per-customer limits, richer scoping and safe concurrency need review | Phase 9 |
| Reviews and returns | Partially implemented and tested | Refund and stock-condition workflows incomplete | Phase 9 |
| Reporting | Partially implemented and tested | Export breadth and reconciliation definitions incomplete | Phase 10 |
| Backups | Implemented but unsuitable for production recovery | Django JSON dump is not PostgreSQL PITR | Phase 13 |
| Monitoring/deployment | Configuration only | No deployed environment or alert evidence | Phase 13 |
| Privacy/compliance | Missing formal implementation | Requires client and qualified legal/compliance decisions | Phase 12 |

## Defect register

| ID | Severity | State | Defect and business impact | Resolution/evidence |
|---|---|---|---|---|
| P0-001 | Critical | Resolved | `User.Role` self-reference prevented all application startup | Privileged roles moved to `User`; checks and tests pass |
| P0-002 | Critical | Resolved | Password-reset views imported forms that did not exist | Forms and focused validation tests added |
| P0-003 | Critical | Resolved | M-Pesa URL routed to a placeholder instead of the callback | Real callback route connected and tested |
| P0-004 | Critical | Resolved | Callback accepted successful payments without checking amount | Expected and received amounts compared; mismatch remains pending for reconciliation |
| P0-005 | Critical | Resolved | Successful online payment skipped fulfilment and marked order complete | Settlement now moves order to `PROCESSING` and records history |
| P0-006 | Critical | Resolved | Terminal payment failure did not restore reserved stock | Atomic cancellation/reversal added with duplicate-callback test |
| P0-007 | High | Resolved | Tests depended on Redis and could contact external notification providers | In-memory test broker/cache configured; incidental tasks are not executed by a worker |
| P0-008 | High | Resolved | Storefront checkout link returned no route | Real authenticated checkout page added |
| P0-009 | Medium | Resolved | Branch route returned `None` through a placeholder lambda | Active branch JSON endpoint and tests added |
| P0-010 | Medium | Resolved | Duplicate POS void URL declaration | Duplicate removed |
| P0-011 | Medium | Resolved | Model choice changes lacked migrations | Analytics/users migrations generated and verified |
| P0-012 | High | Open | Guest checkout is required but API/page require login | Implement signed guest access and guest-safe ownership in Phase 4 |
| P0-013 | High | Open | Production PostgreSQL recovery, deployment and monitoring are unverified | Select host and complete Phase 13 runbooks/tests |
| P0-014 | High | Open | Live payment and messaging integrations are not certified | Sandbox integration suite and controlled acceptance required |
| P0-015 | Medium | Open | Business document names Allauth/Elasticsearch although code uses custom auth/ORM search | Correct business/architecture documentation or approve implementation |

## Corrected delivery plan

1. Phase 0 - stable startup, executable tests, migrations, routing, critical financial safeguards, CI and baseline documentation.
2. Phase 1 - domain constraints, transition services, inventory state model and authorization matrix.
3. Phase 2 - authentication, staff lifecycle, 2FA, impersonation and security regression tests.
4. Phase 3 - storefront, product content, accessibility, SEO and cart persistence.
5. Phase 4 - complete authenticated and guest checkout with secure tracking access.
6. Phase 5 - Daraja sandbox certification, reconciliation, partial/overpayment operations and manual confirmation controls.
7. Phase 6-11 - POS, inventory, fulfilment, marketing/returns, reports and durable notifications.
8. Phase 12-13 - security/privacy assessment and production engineering.
9. Phase 14-15 - cross-layer testing, operating manuals, UAT and release evidence.

Later-phase work must not invalidate the passing baseline.

## Phase 0 implementation checklist

- [x] Restore Django imports and startup.
- [x] Implement missing password-reset forms.
- [x] Run complete tests using isolated infrastructure.
- [x] Reconcile migration drift.
- [x] Connect M-Pesa callback route.
- [x] Validate callback amount.
- [x] Make payment settlement/reversal idempotent.
- [x] Replace branch placeholder route.
- [x] Remove duplicate POS route.
- [x] Repair checkout dead link for authenticated customers.
- [x] Add CI workflow.
- [x] Add local setup and safe environment reference.
- [ ] Complete guest checkout (owned by Phase 4; release-blocking for client MVP).
- [ ] Run the CI workflow on an actual Git host.
- [ ] Complete browser-level checkout verification.
- [ ] Confirm production host and recovery strategy.

## Verification commands

```powershell
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
venv\Scripts\python.exe manage.py test --verbosity 1
venv\Scripts\python.exe -m compileall -q apps config
venv\Scripts\python.exe -m pip check
```

The test environment uses an in-memory Django cache, Celery memory broker and fast test-only password hasher. Production password hashing and Redis configuration are unchanged.

## Client decisions required

1. Choose Railway, Render or another production host; this determines backup/PITR and deployment procedures.
2. Confirm exactly where COD is allowed: delivery, pickup, both, or neither.
3. Approve behaviour for partial and excess M-Pesa payments, including refund/reconciliation ownership.
4. Decide whether riders remain profile-based staff or become a dedicated role.
5. Approve the guest-order tracking mechanism and link expiry.
6. Define customer-data retention, deletion/anonymisation and marketing-consent requirements with qualified compliance advice.
7. Confirm whether WhatsApp fallback is approved and provide an approved template/process.
8. Decide whether Allauth, Google login and Elasticsearch remain requirements or should be removed from the target architecture.
9. Confirm product/brand name and customer-facing language; current templates use inconsistent internal and brand terminology.

## Known limitations

- No production environment was accessed.
- No live provider request was authorized or performed.
- Browser-level JavaScript checkout behaviour has not yet passed an automated browser test.
- Guest checkout is not implemented.
- Passing tests do not establish performance, legal compliance, disaster recovery or operational acceptance.
