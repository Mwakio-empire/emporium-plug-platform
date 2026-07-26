# Store pickup, rider and payment-information decisions

Status: client-supplied business rules recorded on 22 July 2026. Implementation and publication status is stated explicitly below.

## Confirmed operating scope

- Emporium Plug serves delivery destinations within Kenya only. International delivery is not part of the client MVP.
- The two Gaberone Plaza shops are S18 and B03.
- Normal customer and rider collection is from the second floor, S18, unless authorized staff direct the customer elsewhere.
- Paid items are held for two working days from the moment staff mark the packed order ready. Monday through Saturday are working days; Sunday is skipped. The calculation preserves the ready time. Kenyan public holidays are not yet included and require an approved holiday-calendar source.
- A rider/customer should provide a clear item photo and the official payment message for staff-assisted verification.
- Staff must verify payment in the system. A screenshot, forwarded message or typed bank/M-Pesa reference is not proof of settled payment by itself.
- Customers should inspect size, colour and condition before leaving the collection point.

## Client-provided contacts

- 0739 150 246
- 0116 153 335
- 0783 025 355

These operational contact details are published in the site footer. The client confirmed 0116 153 335 as the official WhatsApp ordering number. Channel responsibilities and operating hours beyond Saturday opening still require an operations schedule.

## Client-provided manual payment destinations

- M-Pesa Send Money: 0794 715 595
- ABSA Paybill: business number 303030; account 2048666011; account name Benson Mwakio Mwamburi
- Equity Paybill: business number 247247; account 0794715595; account name Emporium Plug
- Equity account: 0460168644553

These details are recorded for Phase 8 payment-instruction design. They are not hard-coded into templates or treated as automated payment confirmation. Production publication requires the client to reconfirm ownership, display wording and reconciliation responsibility. Sensitive payment references and customer messages must not be logged.

## Returns wording requires review

The supplied notice says that all sales are final and no return or refund is allowed after leaving the shop. This is recorded as the client's current policy, but it is not yet enforced or presented as legally valid. It must be reviewed against applicable Kenyan consumer law and the product-condition/incorrect-item processes before Phase 9. Code must not block legally required remedies merely because this notice exists.

## Remaining operating decisions

- the operators, collection points, parcel restrictions and charges for any future automated town routes;
- who may redirect a pickup away from S18 and how that override is audited;
- payment-verification sources for each manual payment route;
- the complete support and WhatsApp operating hours;
- whether Kenyan public holidays pause the two-working-day pickup deadline.

## WhatsApp boundary

The storefront “Order via WhatsApp” link uses the approved business number 0116 153 335 (`+254116153335`). The setting remains environment-overridable for controlled deployments. WhatsApp starts an assisted conversation only: it does not reserve stock, create a system order, prove payment, or bypass checkout controls. Staff must create/verify the order and payment in the platform.

## Approved launch decision: pickup-first checkout

Public online checkout supports S18 pickup only and selects it by default. Customers who want a parcel sent to another town use the cart-aware WhatsApp link. Staff must confirm the collection point, operator, transport charge, final total and expected arrival before requesting payment. The customer must not place a pickup order and assume it has silently become a parcel order; staff must record the assisted parcel order and its agreed commercial details in the platform.

The launch pickup arrangement is “Pickup after ready notification”; the site must not invent opening-hour windows. Staff marks the order ready and the customer then has the approved two-working-day collection period.
