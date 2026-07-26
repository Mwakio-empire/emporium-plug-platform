# Implemented payment sequences

## STK initiation and callback

```mermaid
sequenceDiagram
    participant Customer
    participant App
    participant DB
    participant Daraja
    Customer->>App: Confirm order and request STK
    App->>DB: Lock order; create INITIATING payment
    App->>Daraja: Initiate STK push
    Daraja-->>App: Merchant + checkout request IDs
    App->>DB: Store IDs; mark PENDING
    Daraja->>App: Public callback
    App->>DB: Lock payment + order
    App->>App: Match IDs, exact amount, unique receipt
    alt Complete matching evidence
        App->>DB: SUCCESS; consume reservation once; order PROCESSING
    else Missing, mismatched, partial or excess evidence
        App->>DB: RECONCILIATION_REQUIRED; order remains PENDING
    end
```

## Missing callback

```mermaid
sequenceDiagram
    participant Worker
    participant Daraja
    participant DB
    Worker->>Daraja: Bounded STK status query
    alt Terminal failure
        Worker->>DB: FAILED; release reservation once; cancel order
    else Query reports success
        Worker->>DB: QUERY_CONFIRMED only
        Note over DB: No receipt/amount evidence; no fulfilment transition
    else Pending or gateway unavailable
        Worker->>Worker: Retry with bounded delay
    end
```

## Manual reconciliation

Authenticated staff must belong to the order branch (super-admin excepted). A branch manager or super-admin re-enters their full password. The verified amount and receipt must meet the same settlement invariants as a callback. The change and reason are committed with an `OperationalAuditRiskLog`; a typed customer reference alone never settles the order.
