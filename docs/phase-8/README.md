# Phase 8: order fulfilment

Status: implemented and automated/browser-test verified. Client UAT remains required before production approval.

## Implemented scope

- Explicit online delivery states from processing, packing and packed through rider assignment, dispatch, out-for-delivery, delivery, customer confirmation/dispute and return.
- Explicit pickup states from processing and packing through ready-for-pickup and collection/cancellation.
- Auditable packing checklist with one check per order line and staff identity/timestamps.
- Branch-scoped, manager-controlled rider assignment. Assignment does not falsely claim dispatch; dispatch occurs when the rider records physical pickup.
- Available-rider and same-branch enforcement with row locks for assignment.
- S18-only customer pickup through the `Branch.offers_customer_pickup` capability. This flag must be enabled only for the real S18 branch during environment setup.
- Six-character pickup code comparison, attempt limiting at the HTTP entry points and branch isolation.
- Ready-for-pickup deadline stored on each order. Two working days means Monday-Saturday; Sunday is skipped. Public holidays are not yet included.
- Expiry cancellation and inventory release use the existing idempotent transition/inventory services.
- Customer tracking includes an order history timeline and S18 pickup deadline.
- Fulfilment notifications are queued only after transaction commit and queue failure does not reverse the business transition.
- WhatsApp assisted-order CTA configured for the approved 0116 153 335 number and environment-overridable through `WHATSAPP_ORDER_PHONE`.
- Original client logo retained. Storefront uses an orange/blue palette, familiar search/cart navigation, clear fulfilment promises and the tagline in the footer.

## Operational boundary

WhatsApp is not an order ledger or payment-verification source. A conversation does not reserve stock. Staff must record the order in this system, revalidate inventory and verify payment through an approved source.

## Production blockers outside code verification

- Client must supply complete WhatsApp and support operating hours.
- Client must configure and validate the real S18 branch capability after migration.
- Automated Kenya-wide parcel selection is deferred; staff must validate each WhatsApp parcel request and record the resulting order. Real S18 pickup slots still require configuration and acceptance tests.
- Client must decide whether public holidays pause pickup deadlines.
- Daraja production approval, controlled payment verification and client UAT remain separate gates.

See [traceability](traceability.md), [state machine](state-machine.md), [browser acceptance](browser-acceptance.md), [verification](verification.md) and [defect register](defect-register.md).
