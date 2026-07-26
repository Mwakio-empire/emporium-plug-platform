# Phase 8 defect register

| Severity | Finding | Resolution/state |
|---|---|---|
| P0 | Pickup checkout accepted every active branch | Replaced with explicit branch pickup capability and enforcement at UI/API/service boundaries |
| P0 | Rider assignment advanced an order as though dispatched | Added separate rider-assigned and dispatched states |
| P0 | Pickup expiry was a fixed 72 hours | Replaced with a persisted two-weekday deadline; legacy ready orders receive a fresh grace period |
| P1 | No packing checklist | Added auditable per-line checklist and staff workspace |
| P1 | Pickup code had no dedicated attempt limit | Added fixed-window limiting and format/constant-time checks |
| P1 | Customer confirmation/dispute did not update the order lifecycle consistently | Centralized status transitions in inbound confirmation handling |
| P1 | Customer tracking lacked a useful lifecycle view | Added chronological timeline and pickup deadline notice |
| P1 | WhatsApp ordering number was ambiguous | Resolved by client: 0116 153 335; CTA now defaults to its normalized Kenyan number |
| P1 | Kenya-wide carrier coverage and rates are not supplied | Open client configuration/UAT item; no unsupported delivery promise is generated |
| P0 | Default test command omitted nested order/logistics suites | Added package markers; default discovery now runs 441 tests instead of 315 |
