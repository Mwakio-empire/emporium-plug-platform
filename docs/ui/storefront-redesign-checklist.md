# Storefront UI redesign checklist

Status: implemented baseline; browser and client UAT still required.

## Customer experience

- [x] Present Emporium Plug as one company-wide store; do not ask customers to understand branch operations.
- [x] Keep the customer path obvious: search or browse, choose a product, add to cart, checkout.
- [x] Use customer-facing language and remove internal terms from storefront copy.
- [x] Show Kenya-wide parcel collection and the S18 pickup location consistently.
- [x] Keep WhatsApp support visible without covering core controls.

## Header and navigation

- [x] Sticky, compact header with brand, search, account and clearly labelled cart.
- [x] Separate the word `Cart` from its numeric badge; no ambiguous `Storefront 0` label.
- [x] Provide a full-width search control on mobile.
- [x] Keep operational staff links available without dominating the customer storefront.

## Homepage and discovery

- [x] Compact hero with one message and one primary action.
- [x] Use the client's original logo artwork where its full composition remains legible.
- [x] Show horizontally scrollable category shortcuts on small screens.
- [x] Put products ahead of filter controls on mobile.
- [x] Collapse mobile filters behind a clear `Filter & sort` control.
- [x] Keep the desktop filter sidebar visible.

## Product cards and details

- [x] Two product cards per mobile row, three on tablet and four in the desktop product area.
- [x] Use consistent square imagery and compact card spacing.
- [x] Keep product name, price, stock and primary action visible without excessive scrolling.
- [x] Send variant products to option selection and allow simple products to add directly.
- [x] Show company-wide availability; remove branch selectors from listing and detail pages.
- [x] Preserve useful empty and out-of-stock states.

## Cart and checkout

- [x] Automatically choose one internal branch that can fulfil the entire basket.
- [x] Prefer an existing cart branch, then a pickup-capable branch, using deterministic selection.
- [x] Never combine stock from several branches to promise an order that no single branch can fulfil.
- [x] Hide internal branch assignment from customers.
- [x] Offer pickup only when the internally assigned branch supports it; otherwise offer delivery.
- [x] Revalidate stock and price at checkout; the checkout API still rejects branch tampering.
- [ ] Design and approve a future inter-branch consolidation workflow before enabling split fulfilment.

## Trust, accessibility and performance

- [x] Preserve semantic headings, labels, alt text, skip link and keyboard-operable controls.
- [x] Use visible focus styles supplied by the existing design system.
- [x] Lazy-load catalogue images.
- [x] Add customer-help, FAQ, delivery/pickup, returns, terms and privacy navigation.
- [x] Label terms as a draft pending client and qualified legal review.
- [ ] Run manual checks with real catalogue imagery and at least 12 representative products.
- [ ] Complete accessibility, device and network-speed testing before production release.
