# Phase 4 Browser Acceptance

Date: 2026-07-21  
Environment: local Django server, local static assets, development-only in-memory cache, no external payment call.

## Passed journeys

1. Guest selected the active branch and added an in-stock product.
2. Checkout displayed item, quantity and subtotal.
3. Delivery zone changed the reviewed total from KES 100.00 to KES 175.00.
4. Switching to pickup hid delivery fields, required a non-expired pickup slot and removed the delivery fee.
5. Final confirmation remained unchecked after fulfilment or price-affecting changes.
6. Guest COD pickup created one order and disabled resubmission.
7. Confirmation displayed protected tracking and optional-registration actions.
8. Tracking token was removed from the visible URL and sent to the API through a header.
9. Tracking displayed only the signed order's status, branch, amount, fulfilment type and items.
10. At a 390 x 844 viewport, checkout and tracking had no horizontal overflow.
11. No browser console errors or warnings remained.

## Defects found and corrected during browser acceptance

- Review-total validation incorrectly depended on the final confirmation checkbox.
- Redis unavailability caused throttle-cache failures and HTTP 500 responses in local development.
- Duplicate checkout padding caused mobile horizontal overflow.

## Exclusions

- No Daraja request was made. M-Pesa sandbox and financial reconciliation are Phase 5.
- The client subsequently approved cash payment for both delivery and pickup. Exact totals and API confirmation enforcement are covered by automated regression tests.
