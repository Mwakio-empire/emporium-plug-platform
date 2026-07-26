# Fulfilment state machines

## Delivery

`PAYMENT_CONFIRMED -> PROCESSING -> PACKING -> PACKED -> RIDER_ASSIGNED -> DISPATCHED -> OUT_FOR_DELIVERY -> DELIVERED`

After delivery, the customer may move the order to `CUSTOMER_CONFIRMED` or `DISPUTED`. A disputed delivery may be resolved to `CUSTOMER_CONFIRMED` or `RETURNED`. Cancellation is permitted only at approved pre-dispatch states. Failed assignment may return a packed order to `PACKED`; physical returns use `RETURNED`.

## Pickup

`PAYMENT_CONFIRMED -> PROCESSING -> PACKING -> PACKED -> READY_FOR_PICKUP -> COLLECTED`

Approved cash pickup may begin at `PENDING -> PROCESSING`; inventory remains reserved until collection. An uncollected ready order becomes `CANCELLED` after its stored deadline and inventory is released exactly once by the shared reversal service.

Every order transition writes `OrderStatusHistory` with the actor, timestamp and note. Delivery-assignment status is separate physical-operation state and is synchronized at rider checkpoints.
