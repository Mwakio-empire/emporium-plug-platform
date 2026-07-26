# ADR-001: Cash fulfilment scope

Date: 2026-07-22  
Status: Accepted

## Decision

Cash payment is permitted for both online delivery and branch pickup orders.

Before an order is created, checkout must display the complete final payable amount and require explicit customer agreement. The creation API independently requires `confirmed: true`; a missing or false value is rejected without creating an order or reserving stock.

The payable calculation remains the system's standard calculation:

`subtotal - valid discount + delivery fee`

- Delivery cash orders include the selected zone's delivery fee.
- Pickup cash orders have no delivery fee.
- Cash is collected during delivery or collection and the order enters processing rather than pending online payment.

## Rationale

The client explicitly approved both fulfilment types. Server-side confirmation enforcement prevents alternate API clients from bypassing the agreement shown by the customer interface.

## Consequences

- Reports must classify these orders as COD without conflating them with walk-in cash sales.
- Fulfilment staff must record actual cash collection and reconciliation in the later POS/operations phases.
- Uncollected or cancelled cash orders must release their reservation exactly once.
