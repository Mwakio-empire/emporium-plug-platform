# Parcel-to-town operations

## Customer promise

“Send to my town” is a prepaid parcel-collection service. It is not doorstep delivery. A customer requests a staff-verified quote from checkout. Emporium Plug confirms the operator, collection point, charge and expected arrival before payment, then hands the packed order to the approved matatu, bus or parcel-office operator in Nairobi. The operator contacts the recipient, who collects from the agreed destination point.

S18 store pickup remains a separate fulfilment method.

## Quote-desk operation

The quote desk operates Monday-Saturday, 8:00 AM-6:00 PM Africa/Nairobi, with a 30-working-minute response target. Sunday and active closure/public-holiday records do not consume that target. Staff work oldest requests first within their own branch and publish the verified operator, exact collection point, fee and expected arrival. Quotes expire 24 hours after publication.

Do not quote from an old receipt or unverified social-media message. Confirm the operator, stage, current fee, luggage/parcel restrictions and compensation process. If the response target passes, the customer sees a reference-specific WhatsApp support link.

## Checkout and pricing

- Customers provide county, town and a preferred collection area; this creates a quote request only.
- Staff publishes the actual operator, exact collection point, fee and expected arrival.
- The platform rechecks current product availability, product/quantity pricing and coupon eligibility before acceptance.
- A stale total must be reviewed and confirmed again.
- Destination, operator and fee are locked onto the accepted order.
- The parcel order must be prepaid. COD is unavailable because the transport operator is not an Emporium Plug payment-collection agent.
- One coupon is allowed. Quantity pricing never stacks with coupons. Discounted/flash items reject coupons unless the coupon explicitly permits them.

## Staff handoff

After confirmed payment, staff process and pack the order. The fulfilment workspace requires the parcel reference and actual transport cost before dispatch. Vehicle registration, operator contact and a dispatch note can also be recorded.

The lifecycle is:

`Pending payment → Payment confirmed → Processing → Packing → Packed → Dispatched → Arrived at destination → Collected`

Arrival should be recorded only after confirmation from the operator or recipient. Collection requires a note stating how it was confirmed. Every transition records the staff actor and time. Customer notification failure does not roll back the operational state.

## Known operational limitations

- No matatu/bus network provides a reliable universal booking API for this workflow. Handoffs and arrival confirmations are recorded by staff.
- The system cannot infer the nearest stage from a county name. Staff and customer must agree on a collection point the recipient can reach.
- Operator availability and fares can change without notice. This is why each quote is verified by staff and expires after 24 hours.
- Parcel loss, damage, prohibited items, compensation and uncollected-parcel rules require signed client policy before launch.

## County and town reference

Checkout lists all 47 Kenyan counties, then loads active towns for the selected county from a maintained KNBS 2019 Population and Housing Census urban-centre baseline. Customers whose town is absent must choose **My town isn't listed** and type it manually. A listed town is reference data only: it does not mean Emporium Plug has approved a transport operator, route, collection point or fee. Every destination still requires staff verification and a quote.

The initial KNBS baseline was derived from an unauthenticated public download. The frozen migration records its revision, but this is not cryptographic proof that KNBS served the downloaded file. Keep a reviewed source copy and checksum for formal refreshes.

Reference-data operators must prepare a UTF-8 CSV whose headers are exactly `county_code,town`, use existing two-digit county codes, test it outside production, and run:

```powershell
.\venv\Scripts\python.exe manage.py import_kenya_towns .\path\towns.csv --source-revision client-YYYY-MM
```

The command validates the complete file before writing, rejects unknown counties and normalized duplicates, and is safe to rerun. A matching KNBS or manually maintained row is reported as skipped and remains unchanged; the CSV importer never takes ownership of its name, activation state or provenance. Use `--deactivate-missing` only when the file is the complete replacement for that same revision. It deactivates missing `CSV_IMPORT` towns belonging to the supplied revision only; it never deletes records, guesses counties or moves towns. Successful admin and import changes clear affected county caches after the transaction commits, while cache unavailability cannot roll back a committed reference-data edit.
