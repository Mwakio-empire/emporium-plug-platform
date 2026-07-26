# Phase 15: client and engineering documentation

Status: documentation set assembled from the verified implementation on 2026-07-26. External provider, staging, recovery and client-acceptance results remain explicitly pending.

This folder is the handover index. Phase documents remain evidence for their own implementation period; this index identifies the current source of truth and avoids copying stale claims.

## Required-document coverage

| # | Required document | Current source |
|---:|---|---|
| 1 | Project purpose and supported scope | [Repository README](../../README.md) |
| 2 | Local setup guide | [Repository README](../../README.md#local-setup) |
| 3 | Environment-variable reference | [Environment reference](environment-reference.md) and [safe example](../../.env.example) |
| 4 | Architecture overview | [Phase 13 architecture](../phase-13/architecture.md) |
| 5 | Entity relationship diagram and data dictionary | [Phase 1 domain model](../phase-1/domain-model.md) |
| 6 | Business-requirements traceability | [Consolidated traceability](requirements-traceability.md) |
| 7 | Role-permission matrix | [Phase 1 role matrix](../phase-1/role-matrix.md) |
| 8 | Order-state transitions | [Phase 8 fulfilment states](../phase-8/state-machine.md) |
| 9 | Inventory/transfer transitions | [Phase 1.5 inventory semantics](../phase-1-5/README.md) and [Phase 7 transfer states](../phase-7/transfer-state-machine.md) |
| 10 | Payment sequences | [Phase 5 payment sequences](../phase-5/payment-sequences.md) |
| 11 | API documentation | [API reference](api-reference.md) |
| 12 | Background-task schedule | [Background tasks](background-tasks.md) |
| 13 | Notification-event catalog | [Phase 11 event catalog](../phase-11/event-catalog.md) |
| 14 | Testing guide | [Testing guide](testing-guide.md) and [manual UAT](../testing/manual-uat-guide.md) |
| 15 | Deployment guide | [Phase 13 deployment runbook](../phase-13/deployment-runbook.md) |
| 16 | Backup/restore runbook | [Phase 13 backup/restore](../phase-13/backup-restore.md) |
| 17 | Incident-response runbook | [Phase 12 incident/breach runbook](../phase-12/incident-breach-runbook.md) |
| 18 | Payment reconciliation | [Payment reconciliation procedure](payment-reconciliation.md) |
| 19 | Staff onboarding and role management | [Staff onboarding](staff-onboarding.md) |
| 20 | POS cashier guide | [POS cashier guide](pos-cashier-guide.md) |
| 21 | Manager operations guide | [Manager guide](manager-operations-guide.md) |
| 22 | Rider guide | [Rider guide](rider-guide.md) |
| 23 | Customer-support guide | [Customer-support guide](customer-support-guide.md) |
| 24 | Known limitations | [Known limitations](known-limitations.md) |
| 25 | Deferred features | [Deferred features](deferred-features.md) |
| 26 | Architecture decision records | [ADR index](adr-index.md) |
| 27 | Release checklist | [Release checklist](release-checklist.md) |
| 28 | Change log | [Change log](changelog.md) |

## Document control

- Update operational guides in the same change that alters a workflow.
- Record a new ADR before changing a business invariant or infrastructure decision.
- Never put credentials, OTPs, customer records or full provider payloads in documentation.
- Mark an item `verified` only when executable or recorded acceptance evidence exists.
- Client names, operational owners, official branch addresses and legal wording require client approval rather than engineering invention.

## Phase 15 exit gate

Repository documentation is complete when links resolve, commands match the repository, the full automated suite passes, and every unverified external claim is labelled. Commercial release remains blocked until the [release checklist](release-checklist.md) is signed with staging, provider, restore and UAT evidence.

See the [Phase 15 defect register](defect-register.md) and [verification record](verification.md) for audit evidence.
