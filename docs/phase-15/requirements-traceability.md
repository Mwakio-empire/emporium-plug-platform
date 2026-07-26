# Consolidated business-requirements traceability

`Complete and verified` means local executable evidence exists; it does not imply provider certification or production approval.

| Capability | Implementation/evidence | State | Remaining gate |
|---|---|---|---|
| Healthy baseline | Phase 0 checks, migrations, CI and full suite | Complete and verified | Repeat on release revision. |
| Users, roles and branch isolation | User constraints, role permissions, Phase 2 authentication/authorization suites | Complete and verified locally | Client staff roster and staging security/UAT. |
| Domain and inventory integrity | Phase 1/1.5 constraints, locked services, audit records | Complete and verified locally | PostgreSQL concurrency suite; DB-level audit immutability remains limitation. |
| Catalog/storefront/cart | Responsive storefront, search/filter/detail/cart/SEO/accessibility tests | Complete and verified locally | Real catalog/media content and client accessibility/UAT. |
| Guest/customer checkout | Pickup-first S18 checkout, cart-aware WhatsApp parcel handoff, coupon feedback, idempotent order creation and signed guest tracking | Complete and verified locally | Configure real S18 slots and complete client UAT. |
| M-Pesa | STK initiation, callback inbox, exact amount/ID checks, idempotency, polling and reconciliation states | Implemented but externally unverified | Daraja sandbox certification and authorized low-value production test. |
| Cash/Paybill | POS cash tender/change/shift; controlled manual Paybill verification | Complete and verified locally | Cashier/manager UAT and real Paybill reconciliation acceptance. |
| POS accountability | Shift-bound sale, manager discount, receipts, reversal void and variance review | Complete and verified locally | Hardware/fiscal decisions and UAT. |
| Intake/inventory/transfers | Hub intake, adjustments, counts, transfer custody and low-stock suppression | Complete and verified locally | Configure official branches; PostgreSQL/load and staff UAT. |
| Fulfilment | Packing, rider assignment, delivery states, S18 pickup/code/deadline | Complete and verified locally | Rider/customer UAT, carriers/rates, public-holiday decision. |
| Promotions/reviews/returns | Coupons/flash sales, verified moderated reviews, eligible returns and stock disposition | Complete and verified locally | Refund remains manual; public/legal wording approval. |
| Reports/reconciliation | Branch-authorized reports, CSV/PDF and explicit schedules | Complete and verified locally | Production-volume reconciliation/load proof and recipient configuration. |
| Notifications | Durable deduplicated attempts, retries, follow-up queue, templates and safe console provider | Complete and verified locally | Approved provider credentials and sandbox certification. |
| Security/privacy | Review, threat model, PII controls, privacy operations and breach runbook | Implemented and locally reviewed | External assessment and qualified Kenyan privacy/legal approval. |
| Production engineering | Render blueprints, environment guards, health, logging, Sentry, deployment/rollback and native backup procedure | Implemented but externally unverified | Provision, alerts, restore, load, latency and failover evidence. |
| Testing | 519-test local suite, browser journeys and manual UAT pack | Complete locally | PostgreSQL lock test, provider/recovery/load/security and client UAT pending. |
| Documentation | Phase 15 indexed engineering/operations/client guides | Complete and locally verified | Client review, named owners and acceptance signatures. |

## Client decisions still required

- Official OTC branch name/address and complete official addresses for all three branches.
- If automated town checkout is reconsidered later: client-approved routes, stages, current fares, parcel restrictions and loss/damage liability. Launch uses staff-assisted WhatsApp instead.
- Whether public holidays pause the two-working-day pickup deadline.
- Legal controller/privacy contact, privacy notice, retention decisions and processor terms.
- Public returns/consumer wording and any Kenyan fiscal/tax-device requirement.
- Named incident, deployment, reconciliation, backup and client-acceptance owners.
