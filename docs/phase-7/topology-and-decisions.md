# Inventory topology and decisions

## Primary stock route

```text
SUPPLIER
   |
   | delivery reference + checked intake
   v
OTC SHOP / RECEIVING HUB
   |                    |
   | approved transfer  | approved transfer
   v                    v
GABERONE PLAZA S18   GABERONE PLAZA B03
```

## Decision: capability, not a hard-coded name

The supplier intake rule is enforced through `receives_supplier_stock`. The application does not look for a branch whose name contains `OTC`. Name matching would be fragile and could put stock into the wrong shop after a rename or spelling change.

## Decision: each shop remains a separate branch

The two Gaberone Plaza shops (S18 and B03) must not share a stock row merely because they occupy one building. Each shop keeps separate:

- on-hand, reserved, damaged and in-transit quantities;
- staff permissions;
- POS shifts and sales;
- transfer receipts and stock counts;
- low-stock alerts and reports.

## Decision: transfers remain generally configurable

The normal route is OTC to either Gaborone shop. The domain service permits an authorized transfer involving any two active branches instead of encoding one permanent route. Supplier intake remains restricted to the configured hub. This supports an exceptional stock rebalance without falsifying it as a supplier delivery.

## Pickup and parcel-delivery handoff

Inventory is owned by the dispatching branch until the fulfilment process consumes the reservation. Customer pickup is normally from S18 on the second floor of Gaberone Plaza, unless authorized staff explicitly direct otherwise. Paid items may be reserved for no more than two working days.

Parcel delivery is Kenya-wide only. International delivery is outside the client MVP. Delivery zones, carrier coverage, fees and service levels remain Phase 8 configuration decisions; the system must not promise a destination until it validates a supported Kenyan delivery option.
