# Constraints, Transactions, and Concurrency

## Database-enforced rules added in Phase 1

- Order money fields cannot be negative.
- Order discount cannot exceed subtotal.
- Order items reference exactly one catalog item, have positive quantity, and non-negative prices.
- Stock references exactly one catalog item and remains unique per item/branch.
- Transfers reference exactly one catalog item, have positive quantity, and use different branches.
- M-Pesa amount is null or non-negative.

These constraints protect data even when writes bypass Django model validation.

## Transaction boundaries

- Inventory changes lock the relevant `Stock` row and write its audit record in the same transaction.
- Order status changes lock `Order` and write status history atomically.
- Payment settlement locks payment and order, then changes both in one transaction.
- Failed/expired payment reversal and terminal order transition occur in one transaction.
- Transfer confirmation changes source stock, destination stock, audits, and transfer status atomically.

## Idempotency

- M-Pesa settlement acts only while its transaction is `PENDING`; duplicate terminal callbacks are no-ops.
- Abandoned-order and unresolved-pickup jobs lock and filter by the expected source state. A repeated job cannot reverse a terminal order again.
- Unique M-Pesa checkout, merchant, and receipt fields prevent duplicate identifiers.

## What local tests do not prove

The local suite uses SQLite. SQLite does not provide PostgreSQL-equivalent row-level `SELECT FOR UPDATE` behavior. The logic and transaction boundaries are tested, but real simultaneous-write behavior must be certified against PostgreSQL with at least:

1. two concurrent deductions against the same stock row;
2. payment callback racing the abandoned-order job;
3. duplicate callback delivery;
4. two managers assigning the same available rider;
5. transfer confirmation racing a sale at the source branch.

Until that PostgreSQL test is run, the project must not claim production-grade concurrency certification.

## Deferred integrity work

- PostgreSQL concurrency certification for the implemented on-hand, reserved, in-transit, and damaged balances.
- Database checks for product/promotion price ranges and date windows.
- Database or trigger-backed immutability for audit/history rows.
- Aggregate returned quantity cannot exceed purchased quantity.
- A complete refund/payment-reversal ledger.
- Category cycle prevention.
