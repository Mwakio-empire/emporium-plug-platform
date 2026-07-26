# State Machines

## Order lifecycle

All persisted changes after order creation must use `orders.transitions.OrderTransitionService`. It obtains a row lock, validates order type and current state, writes the order, and creates `OrderStatusHistory` in one transaction.

```mermaid
stateDiagram-v2
    [*] --> PENDING: M-Pesa order / POS build
    [*] --> PROCESSING: online COD
    PENDING --> PROCESSING: payment confirmed
    PENDING --> COMPLETED: walk-in payment completed
    PENDING --> CANCELLED: payment failed or expired
    PROCESSING --> PACKED
    PROCESSING --> OUT_FOR_DELIVERY: delivery only
    PROCESSING --> READY_FOR_PICKUP: pickup only
    PROCESSING --> CANCELLED
    PACKED --> OUT_FOR_DELIVERY: delivery only
    PACKED --> READY_FOR_PICKUP: pickup only
    PACKED --> CANCELLED
    OUT_FOR_DELIVERY --> DELIVERED
    OUT_FOR_DELIVERY --> CANCELLED
    READY_FOR_PICKUP --> COLLECTED
    READY_FOR_PICKUP --> CANCELLED
    COMPLETED --> VOIDED: walk-in only
    DELIVERED --> [*]
    COLLECTED --> [*]
    CANCELLED --> [*]
    VOIDED --> [*]
```

`PAYMENT_CONFIRMED` remains in the legacy enum but is not used by the active flow. It should be removed only after checking production data and API consumers.

## Delivery assignment lifecycle

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> ASSIGNED: manager assigns rider
    ASSIGNED --> PICKED_UP
    ASSIGNED --> FAILED
    PICKED_UP --> IN_TRANSIT
    PICKED_UP --> FAILED
    IN_TRANSIT --> DELIVERED
    IN_TRANSIT --> FAILED
    FAILED --> ASSIGNED: retry
    FAILED --> RETURNED
    DELIVERED --> [*]
    RETURNED --> [*]
```

A delivery `FAILED` state is not an order cancellation. A later returns/refunds phase must define what `RETURNED` does to payment, stock custody, and customer communication.

## Transfer lifecycle

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CONFIRMED: receiving manager accepts
    PENDING --> REJECTED: receiving manager rejects
    PENDING --> CANCELLED: requester cancels
```

Confirmation deducts from the source and adds to the destination atomically, with two stock audit entries.

