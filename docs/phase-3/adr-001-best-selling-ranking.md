# ADR-001: Best-selling product ranking

## Status

Accepted by the client on 2026-07-21.

## Decision

Rank storefront products by the sum of fulfilled item quantities during the previous 90 days across walk-in, delivery and pickup channels.

Qualifying order statuses are:

- `COMPLETED`
- `DELIVERED`
- `COLLECTED`

Pending, processing, payment-confirmed, cancelled and voided orders do not count. Orders older than 90 days do not count. Direct product lines and variant lines are combined under their parent product.

## Reason

This definition measures recent fulfilled customer demand without allowing abandoned, cancelled or reversed transactions to inflate product popularity. The rolling window prevents lifetime sales from permanently dominating the storefront.
