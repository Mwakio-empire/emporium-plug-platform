# Phase 8 traceability

| Requirement | Implementation | Evidence | State |
|---|---|---|---|
| Packing checklist | `PackingChecklist`, `PackingChecklistItem`, `FulfilmentService` | `test_phase8_fulfilment.py` | Complete and verified |
| Actor/timestamp transitions | `OrderTransitionService`, checklist audit fields | transition and fulfilment tests | Complete and verified |
| S18-only pickup | branch capability plus checkout/service guards | checkout and Phase 8 tests | Complete and verified |
| Two-working-day hold | persisted `pickup_expires_at`, expiry task | pickup lifecycle and working-day tests | Complete and verified for weekdays |
| Rider availability/branch/concurrency | row-locked fulfilment service | rider and Phase 8 tests | Complete and verified on test database |
| Assignment vs dispatch | `RIDER_ASSIGNED`, then `DISPATCHED` on rider pickup | rider-flow tests | Complete and verified |
| Pickup-code safety | format validation, fixed-window limiting, constant-time comparison | logistics tests | Complete and verified |
| Customer confirmation/dispute | inbound SMS transition handler | notification tests | Complete and verified with mocked provider |
| Notification after commit | `transaction.on_commit` wrappers | service tests | Complete and verified |
| Customer tracking | protected status API plus timeline UI | API/template and browser acceptance | Complete and verified |
| WhatsApp assisted ordering | approved 0116 153 335 configuration and conditional CTA | Phase 8 tests | Complete and verified |
| Kenya-wide parcel operation | staff-assisted WhatsApp handoff; internal parcel records retained | checkout page/API and fulfilment tests | Deferred from public self-service until real routes and commercial terms are approved |
| Public-holiday calendar | none | documented decision | Blocked by business decision |
