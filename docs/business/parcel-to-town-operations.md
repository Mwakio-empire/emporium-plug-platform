# Parcel-to-town operations

## Customer promise

“Send to my town” is a prepaid parcel-collection service. It is not doorstep delivery. For the launch MVP it is staff-assisted through WhatsApp rather than offered as public self-service checkout. Emporium Plug confirms the route and charge before payment, then hands the packed order to an approved matatu, bus or parcel-office operator in Nairobi. The operator contacts the recipient, who collects from the agreed destination point.

S18 store pickup remains a separate fulfilment method.

## Route activation

All 47 official Kenyan counties are seeded by migration. A county is not enough to price or fulfil a parcel. A destination becomes selectable only when an authorized operator has configured and activated:

- county and town or market centre;
- destination collection point;
- approved transport operator;
- Nairobi dispatch stage or office;
- current base fee, included weight and additional-kilogram charge;
- expected working-day range;
- rate effective dates; and
- customer collection instructions.

Do not activate a route based on an estimate, old receipt or unverified social-media message. Confirm the operator, stage, fee, luggage/parcel restrictions and compensation process with the client’s operations lead.

## Controlled CSV import

Copy `docs/business/parcel-routes-template.csv` outside the repository, add client-approved rows, and validate it before saving:

```powershell
.\venv\Scripts\python.exe manage.py import_parcel_routes C:\approved-data\parcel-routes.csv --dry-run
.\venv\Scripts\python.exe manage.py import_parcel_routes C:\approved-data\parcel-routes.csv
```

The importer rejects the complete file if any row has an unknown county code, invalid date, invalid amount or broken model rule. Admin edits and CSV imports create audit entries.

## Checkout and pricing

- Customers select county, town and one active collection point.
- Parcel products must have a positive weight.
- The base fee covers the configured included weight.
- Every started kilogram above that weight incurs the configured additional charge.
- Destination names, operator, chargeable weight and fee are locked onto the order.
- Public checkout accepts S18 pickup only. A staff-assisted parcel order must be prepaid after the route and final amount are confirmed. COD is not available because the transport operator is not an Emporium Plug payment-collection agent.

## Staff handoff

After confirmed payment, staff process and pack the order. The fulfilment workspace requires the parcel reference and actual transport cost before dispatch. Vehicle registration, operator contact and a dispatch note can also be recorded.

The lifecycle is:

`Pending payment → Payment confirmed → Processing → Packing → Packed → Dispatched → Arrived at destination → Collected`

Arrival should be recorded only after confirmation from the operator or recipient. Collection requires a note stating how it was confirmed. Every transition records the staff actor and time. Customer notification failure does not roll back the operational state.

## Known operational limitations

- No matatu/bus network provides a reliable universal booking API for this workflow. Handoffs and arrival confirmations are recorded by staff.
- The system cannot infer the nearest stage from a county name. Customers choose a town they can reach.
- Operator availability and fares can change without notice. Staff must deactivate affected routes immediately.
- Parcel loss, damage, prohibited items, compensation and uncollected-parcel rules require signed client policy before launch.
