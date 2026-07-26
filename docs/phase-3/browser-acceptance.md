# Phase 3 Browser Acceptance Evidence

Date: 2026-07-21

Environment: local Django development server with the pinned local frontend build.

## Verified journey

1. Loaded the storefront using local `storefront.css`, local HTMX and local page JavaScript.
2. Confirmed the server-rendered product grid and empty cart remained in their correct containers after HTMX load events.
3. Opened the cart from the unique `View cart` button.
4. Confirmed the dialog became visible, `aria-hidden` changed to `false`, `inert` was removed and focus moved to the Close button.
5. Pressed Escape while the Close button was focused.
6. Confirmed the dialog became hidden, `aria-hidden` returned to `true`, `inert` was restored and focus returned to the original View cart button.
7. Selected `Best selling` and confirmed the product grid updated without replacing the cart content.
8. Set the viewport to 390 x 844 and confirmed there was no horizontal page overflow.
9. Confirmed the browser reported no JavaScript console errors.

## Defect discovered and resolved

The initial browser run found that the product-grid load request inherited the parent cart target and could replace cart content with product-card markup. The grid now declares `hx-target="#product-grid-target"`, with a server-rendered regression assertion.
