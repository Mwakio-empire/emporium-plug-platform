# M-Pesa and cash reconciliation procedure

## Daily ownership

The branch manager owns branch exceptions; the super admin owns cross-branch/provider escalation. A typed reference, screenshot or customer message is not proof of settlement.

## M-Pesa exception workflow

1. Open the payment/operations record and identify the order, expected amount, checkout request ID, payment state and retained callback/query evidence.
2. Confirm the order remains unfulfilled while payment is `PENDING`, `QUERY_CONFIRMED` or `RECONCILIATION_REQUIRED`.
3. Compare against the authorized Safaricom statement/portal using checkout request, business short code, receipt, phone/account reference, amount and time. Do not rely on an SMS screenshot.
4. For a confirmed exact settlement, authorized staff select the payment, enter the verified receipt/amount, reason and source, then a branch manager or super admin re-enters their full password.
5. The service locks payment/order rows, rechecks amount and uniqueness, records the operational audit event, consumes reserved stock once and moves the online order to processing.
6. For partial, excess, mismatched, duplicated or unknown money, leave the order out of fulfilment and escalate. Do not turn an exception into ordinary success.
7. For a confirmed terminal failure/timeout, allow the payment service/task to fail the payment, cancel the order and release reservations exactly once. Verify the stock audit reference.
8. Record the resolution, actor, evidence source and follow-up in the daily report.

Unknown or malformed callbacks remain retained events. Resolve them through the dedicated event endpoint only after identifying whether they belong to an existing payment; never delete evidence to clear a queue.

## Duplicate and delayed evidence

- Repeated callback with the same checkout/receipt must be idempotent.
- Poll success without receipt/amount remains `QUERY_CONFIRMED`, not paid.
- A later complete callback may settle a query-confirmed payment once.
- A callback after a terminal cancellation requires reconciliation; do not restore/consume stock twice.

## Cash and Paybill

- Walk-in cash: reconcile opening cash plus completed cash sales against counted closing cash. Record tender/change on each receipt.
- COD/collection cash: payment remains due until the authorized fulfilment step records collection; it must not be treated as prepaid.
- Paybill/manual reference: staff verification requires an approved source and manager re-authentication. Customer-entered text is only a lead for investigation.
- Voids are reversals, never deletion. They require manager password, reason, stock restoration once and inclusion in shift/void reporting.

## End-of-day evidence

Retain the system payment-method split, failed/reconciliation list, manual confirmations, shift reconciliation, voids and provider settlement total. Investigate every difference before closing the operational day. Never export full callback payloads or unnecessary customer personal data.

Production reconciliation remains unverified until Daraja sandbox certification and a written, low-value production verification authorization are completed.
