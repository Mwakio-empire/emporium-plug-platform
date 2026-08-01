# Kenya County and Town Selector Design

**Date:** 2026-08-02

**Status:** Approved for implementation

**Scope:** Delivery-quote destination selection at customer checkout

## Objective

Replace the free-text county and town fields in the delivery-quote form with a dependable Kenya-wide, county-dependent selector. The interface must reduce spelling errors without preventing a customer from requesting a quote for a legitimate town that is absent from the reference data.

Selecting a destination remains a quote request. It does not promise that a parcel operator serves the town, calculate an unverified fee, create an order, reserve stock or initiate payment.

## Reference-data policy

- Retain `KenyaCounty` as the source of the 47 county options.
- Add a `KenyaTown` reference model linked to exactly one county.
- Seed the initial town list from the Kenya National Bureau of Statistics 2019 Population and Housing Census urban-centre dataset.
- Treat the list as a maintained operational reference, not a permanent legal claim that every Kenyan settlement is present. Town and urban-area classifications can change through county decisions and Gazette notices.
- Provide an explicit unlisted-town fallback so reference-data omissions never block a customer.
- Record the dataset source and revision in the migration and operations documentation.

## Data model

`KenyaTown` will contain:

- a database identifier;
- `county`, protected by a foreign key to `KenyaCounty`;
- the customer-facing town name;
- a normalized name used to prevent case-only duplicates within a county;
- an activation flag so incorrect or retired options can be hidden without deleting historical meaning;
- optional source metadata for maintainers.

The database will enforce uniqueness of the normalized town name within a county. Existing `DeliveryQuoteRequest.county` and `DeliveryQuoteRequest.town` text fields remain snapshot fields so historical requests do not change when reference data is updated.

## Customer interface

1. The county field is a required dropdown containing the active 47 counties.
2. The town field starts disabled with the instruction "Select a county first."
3. Selecting a county loads only active towns belonging to that county.
4. The town control supports keyboard navigation and quick name matching. Native, accessible controls are preferred unless browser testing proves a custom combobox is necessary.
5. The final town option is "My town isn't listed." Selecting it reveals a required manual town field.
6. Changing county clears any previously selected town and manual town value.
7. Loading, empty-list and network-failure states explain what the customer can do. A loading failure offers retry and the unlisted-town fallback; it does not discard the remaining checkout form.
8. "Preferred collection area" stays free text because stages, offices and convenient collection points vary and must be confirmed by staff.

## API and server validation

A public, read-only logistics endpoint will return active towns for one valid county code. Results will be consistently ordered, contain only the identifiers and names required by checkout, and be safe to cache. Invalid or inactive county codes return a clear client error.

Delivery-quote creation will accept:

- `county_code`;
- either `town_id` or an explicit unlisted-town marker with `custom_town`;
- the existing recipient and preferred-collection-area fields.

The server will resolve and validate the destination independently of the browser:

- county must be active and exist;
- a selected town must be active and belong to the submitted county;
- a selected-town request may not silently substitute custom text;
- an unlisted-town request requires trimmed, length-limited custom text;
- control characters and empty values are rejected;
- the resolved county and town names are passed to the existing quote service and stored as snapshots.

Tampered county/town combinations must fail without creating a quote request.

## Administration and maintenance

Authorized administrators can activate, deactivate and correct town reference records through Django administration. Deletion is not the normal maintenance path. A documented import/update command will validate duplicates and county relationships before changing data. Updating the town reference list must not rewrite existing quotes or orders.

## Security and privacy

- The location endpoint exposes public geographic reference data only.
- Apply the existing anonymous API throttling policy and cache successful lookup responses.
- Do not expose customer data, quote data, route pricing or internal parcel operators through the lookup endpoint.
- All quote-creation throttles, guest-access controls and transaction boundaries remain in force.

## Testing

Automated tests will verify:

- all 47 active counties remain available;
- towns are returned only for the requested county and in deterministic order;
- inactive counties and towns are excluded;
- checkout renders the dependent controls and unlisted-town fallback;
- selecting a different county clears stale town state;
- valid selected towns create quote requests with normalized snapshot names;
- valid unlisted towns create quote requests through the explicit fallback;
- missing values, invalid identifiers, inactive records and cross-county tampering are rejected;
- failed validation creates no quote and reserves no stock;
- existing delivery-quote, pickup and checkout tests continue to pass;
- keyboard, mobile and error-state behavior passes manual browser testing.

## Documentation impact

Update the parcel-to-town policy, API reference, requirements traceability matrix, manual UAT guide and changelog. Document the data source, update procedure and the fact that staff still verifies availability, operator, collection point, fee and arrival estimate before payment.

## Out of scope

- automatic route or nearest-stage selection;
- automatic delivery-price calculation from the town list;
- map/GPS address lookup;
- doorstep-delivery promises;
- silently treating every listed town as an approved parcel route.

These capabilities require verified operator and commercial data and are not implied by a geographic selector.
