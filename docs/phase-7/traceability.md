# Phase 7 traceability

| Requirement | State | Evidence |
|---|---|---|
| Supplier stock intake | Complete and verified locally | Hub capability, intake service/API and idempotency tests. |
| Reasoned adjustments | Complete and verified locally | Correction, theft and damage-quarantine service. |
| Per-branch stock | Complete and verified | Existing constraints plus branch-scoped operations. |
| Variant stock | Complete and verified | Intake, transfer and stock services support variants. |
| Low-stock thresholds | Complete and verified locally | Product threshold evaluated per branch stock row. |
| Alert spam prevention | Complete and verified locally | Durable transition state; repeated sweep test. |
| Transfer request | Complete and verified | Destination or source branch controller may request. |
| Source approval | Complete and verified | Source-branch authorization and state test. |
| Dispatch/in transit | Complete and verified | Atomic custody transition and audits. |
| Partial/full receipt | Complete and verified | Immutable receipts and two-stage receipt test. |
| Rejection/cancellation | Complete and verified | Reason required; no stock mutation before dispatch. |
| Transfer history | Complete and verified | Actors, timestamps, notes, receipts and audits. |
| Cycle/spot count | Complete and verified locally | Snapshot, counted quantities, stale-count rejection and correction audit. |
| Staff inventory workspace | Complete and verified locally | Role-restricted intake, transfer, adjustment and count forms; automated and browser journey evidence. |
| Discrepancy reporting | Complete at record level | Count-line variance and correction audit are persisted. |
| Bulk import/export | Deferred - business decision | Client must confirm need and file contract. |
| PostgreSQL race evidence | Deferred staging gate | SQLite skip is explicit; not claimed as passed. |
