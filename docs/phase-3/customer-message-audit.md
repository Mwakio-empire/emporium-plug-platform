# Customer message audit

Date: 2026-08-01

## Standard used

Every customer message should state what happened, whether their cart/order/payment is safe, and what they can do next. Normal customer screens must not expose internal field names, enum values, tracebacks, backend terminology or raw validation-list formatting.

## Reviewed surfaces

| Surface | Result |
|---|---|
| Global toast | Mobile width is bounded to the viewport; text wraps normally; headings use Done, Please check this, Please note or Update. |
| Restock alert | Active alert replaces the signup form and states channel, exact item, one-shot behaviour and that stock is not reserved. |
| Cart actions | Invalid quantity/item requests use plain instructions rather than API field names. |
| Checkout creation/review | Expired/reused checkout state, changed branch availability, minimum quantities and order uncertainty explain the safe next action. |
| Coupon/quantity price | The customer is told that the two discounts cannot be combined. |
| M-Pesa initiation/manual reference | Required information is named in customer language; an unavailable order directs the customer to tracking. |
| Account/profile/privacy | Existing forms flatten validation messages and explain success/failure outcomes. |
| Order tracking/cancellation | Existing copy describes stock release, payment state, tracking and reorder/cancellation actions. |

Staff operations retain precise operational wording where it helps trained staff and audit handling; that wording is not presented as storefront copy.
