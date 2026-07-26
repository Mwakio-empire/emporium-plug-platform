# Phase 3 Defect Register

## Resolved

- **P0 - Hidden catalog leakage:** public catalog access now requires an active product and a visible complete category ancestor path.
- **P0 - Cross-branch cart promise:** the storefront shows company-wide availability, but the cart automatically binds to one branch that can fulfil every line. Stock is never summed across branches to promise an unfulfillable basket.
- **P1 - Incorrect simple-product cards:** in-stock simple products have a valid add action; variant products require an option.
- **P1 - Incomplete product content:** ordered galleries, alt text, specifications and administration support are implemented.
- **P1 - Session-only customer carts:** authenticated carts persist by customer/branch and same-branch guest carts merge on login.
- **P1 - Incomplete SEO:** canonical URLs, product descriptions, JSON-LD, sitemap and robots policy are implemented.
- **P1 - Public CDN runtime dependency:** Tailwind and HTMX are pinned, built and served locally.
- **P1 - API/HTML stock mismatch:** REST list/detail stock can be scoped to the same active branch and exposes available quantity.
- **P1 - Silent 24-product cutoff:** server-rendered pagination provides result and page counts.
- **P2 - Missing category navigation:** a recursive customer-facing category tree is rendered.
- **P2 - Internal customer copy:** engineering language was removed from Phase 3 pages.
- **P2 - Sales ordering undefined:** the client approved a rolling 90-day fulfilled-quantity definition; direct and variant sales across all channels are combined.
- **P2 - Cart keyboard evidence incomplete:** browser acceptance now proves focus transfer, Escape dismissal and focus restoration.
- **P1 - HTMX target inheritance:** browser testing found product-grid load responses could overwrite the cart. The grid now has an explicit self-target and regression assertion.

## Deferred by phase boundary

### Phase 4 - Checkout end-to-end proof

Cart stock and price revalidation exists, but authenticated and guest checkout completion, duplicate submission and simultaneous-final-unit behavior are Phase 4 exit criteria and must not be represented as Phase 3 proof.
