# Delivery Quotes and Controlled Coupon Stacking Design

## Purpose

+Emporium Plug will support structured requests for parcel transport to Kenyan towns without pretending that it offers automated doorstep delivery. Customers can request a transport quote, staff can publish verified collection details and a fee, and the customer can accept the final amount before an order or stock reservation exists.

## Operating policy

- Quote review hours are Monday through Saturday, 8:00 AM to 6:00 PM, Africa/Nairobi.
- Sundays and configured Kenyan public holidays are closed.
- The response target is 30 working minutes.
- Requests may be submitted at any time. An after-hours request is due 30 working minutes after the next opening time.
- WhatsApp remains available as help. It becomes the prominent escalation after the response target is missed.
- A request is not an order, does not reserve stock and does not prove payment.
- Parcel orders are prepaid. Cash on delivery is not available because the parcel operator is not an Emporium Plug collection agent.

## Customer workflow

1. The customer selects **Send to my town** from checkout.
2. The customer provides county, town, preferred collection area, name, phone, optional email and notes.
3. The platform captures an immutable display snapshot of the current cart and issues an unguessable quote reference plus protected access link.
4. The status page displays `Requested`, `Being reviewed`, `Quote ready`, `Accepted`, `Declined`, `Expired` or `Cancelled` using customer-facing copy.
5. During working hours the page shows the response deadline. When overdue, it displays a WhatsApp link prefilled with the quote reference.
6. Staff records the transport operator, exact collection point, transport fee and expected arrival, then publishes the quote.
7. Publication starts a 24-hour validity window and queues SMS/email notification after the database transaction commits.
8. The customer reviews the complete current total and accepts or declines. Before acceptance, stock, product prices and coupon eligibility are revalidated. Any change is displayed and requires explicit confirmation.
9. Acceptance creates one idempotent prepaid parcel order, reserves inventory once and links the order to the quote. Repeated acceptance returns the same order.

## Ownership and security

- Authenticated customers may access only their own requests.
- Guests use a signed, expiring token; references alone grant no access.
- Request creation, status reads and acceptance are throttled.
- Staff access is limited to active privileged users in the assigned branch, with super-admin override.
- Quote publication, changes, acceptance, decline, cancellation and expiry are auditable.
- Customer data and signed access tokens must not be written to logs.

## Pricing policy

- One coupon may be redeemed per order.
- Wholesale quantity pricing never stacks with a coupon.
- A coupon is ineligible when any line uses a flash-sale price unless its `allow_discounted_items` control is enabled.
- When enabled, the coupon discount is calculated from the already-discounted subtotal.
- Manual manager discounts never stack with coupons.
- The customer receives separate figures for regular-price value, product/flash savings, coupon savings, parcel fee and final payable total.
- Coupon usage is consumed only when the order is created, never when a quote is requested or merely published.

## Data lifecycle

- Cart snapshots exist for staff context and customer review; they are not trusted as current prices or stock.
- A published transport fee is fixed until quote expiry.
- Product prices, availability and coupons are current-state values at acceptance.
- Expired, declined and cancelled requests do not mutate stock or coupon counters.
- If revalidation changes the final product total, the customer sees the difference and must confirm the updated total before order creation.

## Operational interface

- The fulfilment workspace lists open quote requests oldest-first and highlights overdue requests.
- Staff can mark a request as being reviewed and publish the verified route details.
- Public holidays are managed as dated closures instead of being hard-coded.
- Published quotes display the responsible staff member and timestamps in the internal audit view, not to the customer.

## Out of scope

- Doorstep delivery promises.
- An invented national route/fee table.
- Cash on delivery for town parcels.
- Stock reservation before customer acceptance.
- Automated refunds or operator integrations.
