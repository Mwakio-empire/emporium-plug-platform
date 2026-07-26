# ADR-001: C2B Paybill launch scope

Status: Accepted - 2026-07-26

## Context

The business context contains two different walk-in Paybill flows. The POS section
allows staff to enter and verify an M-Pesa reference, while the payment section asks
for a Daraja C2B callback that matches an open sale by amount and a time window.
The current application implements the first flow with branch-scoped manager
re-authentication and an immutable risk record. It does not expose C2B validation or
confirmation callbacks.

Matching only by amount and time is not safe enough for a financial mutation. Two
customers can pay the same amount during the same period, and the available business
payment details do not establish that Emporium Plug controls a Safaricom shortcode
enabled for Daraja C2B callbacks.

## Decision

Defer automatic C2B Paybill matching from the launch MVP. Retain M-Pesa STK Push for
online payment and the audited manager-verified Paybill flow for walk-in sales. A
typed reference, message or screenshot is never proof of payment; staff must verify
the transaction against an authorized provider portal or statement.

Do not implement the proposed amount-and-time matcher. A future C2B integration may
settle automatically only when all of the following are available:

- a client-controlled, C2B-enabled Safaricom business shortcode;
- registered validation and confirmation URLs for the deployed environment;
- a pending sale created before payment with its unique order number used as the
  customer account reference;
- exact order-reference and amount matching plus a unique provider transaction ID;
- durable, idempotent callback intake and an ambiguity/reconciliation queue;
- tested handling for duplicates, unknown references, partial payments,
  overpayments, callback delay and callback replay; and
- completed Daraja sandbox certification followed by an explicitly authorized
  low-value production verification.

## Consequences

- Launch does not falsely claim automatic walk-in Paybill reconciliation.
- Walk-in Paybill confirmation takes longer and requires an authorized manager.
- Every confirmation retains the cashier, manager, branch, amount, receipt, reason
  and timestamp for reconciliation.
- The original automatic C2B requirement is an explicitly accepted deferral, not an
  unnoticed missing feature.
- Adding C2B later requires a new reviewed implementation phase and provider
  onboarding; this ADR must not be reinterpreted as production certification.
