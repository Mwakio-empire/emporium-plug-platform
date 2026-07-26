# Phase 10 defect register

| Severity | Finding | Resolution/state |
|---|---|---|
| P0 | Existing reports omitted `CUSTOMER_CONFIRMED`, causing revenue to disappear after customer confirmation | Added to centralized recognized statuses |
| P1 | Reports used order creation date rather than successful-sale transition time | First successful transition is now the recognition date |
| P1 | Existing report surface covered only staff shift and branch daily totals | Added consolidated operations workspace/API |
| P1 | Scheduled PDF was sent unconditionally to all super admins or an invented fallback address | Replaced with explicit recipient schedules |
| P1 | Existing executive generator used stale completed-only and all-branch assumptions | New scheduled path uses the authoritative operations service |
| P1 | Failed report delivery had no durable operational record | Added immutable per-period delivery outcome |
| P2 | PostgreSQL query performance is not load-tested | Remains a production-engineering gate |
