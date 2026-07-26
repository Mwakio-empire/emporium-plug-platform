# Phase 5 — M-Pesa and cash payments

Status: **implementation verified; external certification pending**. This phase is not production-certified and no live payment is authorized.

## Scope

This phase hardens M-Pesa initiation, callback reconciliation, polling, failure handling, manual-reference review, and POS cash accounting. Ordinary tests mock external providers. Daraja sandbox certification and an explicitly authorized low-value production check remain deployment gates.

## Approved business decisions

- Cash is permitted for delivery and branch pickup. Checkout must show the full payable amount and require explicit customer confirmation.
- Sensitive payment corrections use the manager's full password re-authentication, with throttling and audit logging. A reusable manager PIN is not being introduced.
- A customer-entered Paybill reference is a reconciliation lead, not proof of payment.

## Exit gate

- A callback cannot confirm a payment without an exact amount and unique receipt.
- Callback merchant and checkout identifiers must match the initiated request.
- Polling success cannot bypass callback financial evidence.
- Underpayments and overpayments remain unfulfilled and require reconciliation.
- Duplicate callbacks and terminal failures cannot consume or release stock twice.
- Manual references never replace Daraja request identifiers or receipt evidence.
- Cash POS records amount received and change due and rejects insufficient tender.
- Abandoned pending orders are swept by Celery Beat.
- Focused and full automated suites, Django checks, migration drift, and syntax checks pass.

## Deliberate limitations

- Formal clock-in/clock-out shift association is Phase 6. Phase 5 records the cashier and branch and feeds the existing reconciliation calculation; it will not invent an active-shift lifecycle.
- Provider query success does not include enough receipt-level evidence to settle an order. It is recorded for reconciliation while awaiting the callback or authorized manual verification.
- A process crash after Daraja accepts a push but before its identifiers are saved is an external-system uncertainty that cannot be eliminated without a provider-supported idempotency key. It must be monitored and reconciled.
- Production readiness cannot be claimed until sandbox certification, monitoring, incident procedures, and authorized production verification are complete.
- Malformed, unknown, conflicting and mismatched callbacks now enter a durable, deduplicated operations queue. Resolution requires manager re-authentication, a reason and an immutable audit entry.

## Implemented result

- Local payment lifecycle exists before the outgoing STK request and prevents an ordinary retry from sending a second prompt.
- Success settlement requires matching request identifiers, exact expected amount, and a unique provider receipt.
- Query success enters `QUERY_CONFIRMED`; it cannot consume stock or advance fulfilment without receipt-level evidence.
- Conflicting, partial, excess, malformed, or incomplete evidence enters reconciliation instead of ordinary success.
- Customer-entered fallback references have their own unique field and never replace provider identifiers or receipts.
- Manual confirmation requires authenticated staff, branch isolation, manager password re-authentication, exact evidence, a reason, and immutable risk/audit records.
- Walk-in Paybill completion has the same manager-verification control. The actual cashier remains recorded as processor.
- POS cash records amount received and change due and rolls back the sale and stock mutation for insufficient tender.
- Payment records are view-only in Django Admin; staff cannot fabricate or delete them there.
- The abandoned pending-order sweep is registered in Celery Beat every five minutes.

See [verification.md](verification.md) for executable results and [payment-sequences.md](payment-sequences.md) for the implemented flows. Manual certification procedures are in [manual-certification-runbook.md](manual-certification-runbook.md); record results with [manual-test-results-template.md](manual-test-results-template.md). PostgreSQL-only verification is documented in [postgresql-concurrency.md](postgresql-concurrency.md).
