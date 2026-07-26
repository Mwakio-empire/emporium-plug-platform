# Transfer state machine

```text
REQUESTED
  |-- source approves ----------> APPROVED
  |-- source rejects -----------> REJECTED
  |-- authorized cancellation --> CANCELLED

APPROVED
  |-- source dispatches --------> DISPATCHED
  |-- authorized cancellation --> CANCELLED

DISPATCHED
  |-- partial quantity received -> PARTIALLY_RECEIVED
  |-- all quantity received ----> RECEIVED

PARTIALLY_RECEIVED
  |-- another partial receipt --> PARTIALLY_RECEIVED
  |-- remaining qty received ---> RECEIVED
```

Rules:

- Request and approval do not move stock.
- Dispatch atomically moves quantity from source on-hand to source in-transit.
- Receipt atomically reduces source in-transit and increases destination on-hand.
- Each partial receipt has its own immutable receipt and stock audit reference.
- A dispatched transfer cannot be cancelled; discrepancies require receipt investigation rather than deleting custody evidence.
- Dispatch rechecks available stock under a database row lock.
