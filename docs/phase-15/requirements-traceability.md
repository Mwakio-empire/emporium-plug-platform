# Consolidated business-requirements traceability

`Complete and verified` means local executable evidence exists; it does not imply provider certification or production approval.

| Capability | Implementation/evidence | State | Remaining gate |
|---|---|---|---|
| Healthy baseline | Phase 0 checks, migrations, CI and full suite | Complete and verified | Repeat on release revision. |
| Users, roles and branch isolation | User constraints, 15-character customer passphrases, phone/email login, staff 2FA, authenticated password change, role permissions and Phase 2 authentication/authorization suites | Complete and verified locally | Witnessed Brevo/Africa's Talking delivery test, client staff roster and staging security/UAT. |
| Domain and inventory integrity | Phase 1/1.5 constraints, locked services, audit records | Complete and verified locally | PostgreSQL concurrency suite; DB-level audit immutability remains limitation. |
| Catalog/storefront/cart | Responsive storefront, structured Size/Colour/Capacity option combinations, per-SKU stock/price/image support, configurable product MOQ and percentage quantity tiers across mixed variants, search/filter/detail/cart/SEO/accessibility tests, wishlist, and rate-limited one-shot SMS restock requests for exact products/variants | Complete and verified locally | Client must configure/approve real quantity thresholds and discounts; replace DEMO-SKU fixtures with client-approved catalogue, prices, images and opening stock; certify customer SMS delivery and complete client accessibility/UAT. |
| Guest/customer checkout | Pickup-first S18 checkout; all 47 counties; county-dependent KNBS 2019 town reference with server validation and an unlisted-town fallback; protected quote access, working-hours SLA, staff publication, 24-hour expiry and explicit current-total acceptance; controlled coupon stacking; idempotent order creation; signed guest tracking; ten-minute unpaid-order cancellation grace period | Complete in focused local tests | Run complete regression suite; desktop/mobile selector UAT; retain reviewed source provenance; configure real S18 slots, closure dates and provider delivery; complete client UAT. |
| M-Pesa | STK initiation, callback inbox, exact amount/ID checks, idempotency, polling and reconciliation states | Implemented but externally unverified | Daraja sandbox certification and authorized low-value production test. |
| Cash/Paybill | POS cash tender/change/shift; controlled manual Paybill verification | Complete and verified locally for approved launch scope | Cashier/manager UAT and real Paybill reconciliation acceptance. Automatic C2B matching is explicitly deferred by Phase 5 ADR-001. |
| POS accountability | Shift-bound sale, manager discount, receipts, reversal void and variance review | Complete and verified locally | Hardware/fiscal decisions and UAT. |
| Intake/inventory/transfers | Hub intake, adjustments, counts, transfer custody, low-stock suppression and idempotent official three-branch configuration | Complete and verified locally | Apply the approved branch command after staging/production migrations; PostgreSQL/load and staff UAT. |
| Fulfilment | Packing, rider assignment, delivery states, S18 pickup/code/deadline | Complete and verified locally | Rider/customer UAT, carriers/rates, public-holiday decision. |
| Promotions/reviews/returns | Coupons/flash sales, verified moderated reviews, eligible returns and stock disposition | Complete and verified locally | Refund remains manual; public/legal wording approval. |
| Reports/reconciliation | Branch-authorized reports, CSV/PDF and explicit schedules | Complete and verified locally | Production-volume reconciliation/load proof and recipient configuration. |
| Notifications | Durable deduplicated attempts, retries, follow-up queue, templates and safe console provider | Complete and verified locally | Approved provider credentials and sandbox certification. |
| Security/privacy | Review, threat model, PII controls, privacy operations and breach runbook | Implemented and locally reviewed | External assessment and qualified Kenyan privacy/legal approval. |
| Production engineering | Render blueprints, environment guards, health, logging, Sentry, deployment/rollback and native backup procedure | Implemented but externally unverified | Provision, alerts, restore, load, latency and failover evidence. |
| Testing | 710-test suite passes on SQLite and PostgreSQL, focused delivery-quote/stacking regressions and manual UAT pack | Automated suite complete on the current working tree | Committed staging rerun, complete authenticated browser/accessibility UAT, provider/recovery/load/security and client acceptance remain pending. |
| Documentation | Phase 15 indexed engineering/operations/client guides | Complete and locally verified | Client review, named owners and acceptance signatures. |

## Client decisions still required

- Official OTC branch name/address and complete official addresses for all three branches.
- Client-approved transport operators, quote ownership rota, parcel restrictions and loss/damage liability wording. Staff determines each current route and fare; the platform does not invent a static route table.
- Client-approved ownership and revision schedule for the Kenya town reference. The initial KNBS 2019 baseline came from an unauthenticated public download, so the frozen revision is not cryptographic source-authenticity evidence. A listed town does not approve a route or fee.
- Whether public holidays pause the two-working-day pickup deadline.
- Legal controller/privacy contact, privacy notice, retention decisions and processor terms.
- Public returns/consumer wording and any Kenyan fiscal/tax-device requirement.
- Named incident, deployment, reconciliation, backup and client-acceptance owners.
