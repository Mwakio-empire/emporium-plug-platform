# Phase 3 - Catalog and Storefront MVP

## Status

Complete on 2026-07-21. The final Django suite executed 268 tests: 267 passed and one PostgreSQL-only row-lock test was intentionally skipped under SQLite. Django checks, migration drift, Python and JavaScript syntax validation, dependency checks, the identity-collision audit, npm audit, the pinned frontend build and the critical browser journey pass.

## Verified behavior

- Public catalog queries expose only active products whose complete category ancestor path is visible.
- Search, category, descendant-category, branch, price, availability and safe sorting filters can be combined.
- Nested category navigation and 24-item pagination are server-rendered.
- The selected active branch persists and scopes product, cart, checkout and REST stock availability.
- The cart prevents mixed-branch items and persists per customer and branch after authentication.
- Same-branch guest carts merge into the customer's saved cart on login.
- Product pages support gallery images with required alt text, structured specifications, variants, branch stock, quantity limits, reviews and related products.
- Per-product metadata, canonical URLs, Product JSON-LD, sitemap and robots policy exist.
- Storefront filters and cart mutations have ordinary request/response fallbacks when HTMX is unavailable.
- Tailwind and HTMX are pinned and served locally; ordinary storefront rendering no longer depends on public CDNs.
- Best-selling order uses the client-approved rolling 90-day fulfilled-quantity definition across all sales channels.
- Browser acceptance verified cart isolation, open/close focus behavior, Escape dismissal, HTMX sorting, local assets, zero console errors and no horizontal overflow at 390 x 844.

## Architecture

`catalog.storefront` is the public-query boundary for effective category visibility, company-wide stock annotations and safe filter parsing. Customers do not select a branch. `UnifiedSessionCartService` assigns one internal branch that can fulfil the complete basket and owns guest and authenticated cart invariants. Authenticated snapshots remain stored by customer and internal fulfilling branch in `CustomerCart`.

Frontend assets are reproducible from `package-lock.json`. `npm.cmd run build` compiles Tailwind into `static/core/storefront.css` and copies the pinned HTMX distribution into `static/vendor/htmx.min.js`.

## Phase boundary

Phase 3 provides a coherent catalog, product-detail and cart experience. Complete guest/authenticated checkout, payment progress and simultaneous-final-unit checkout proof remain Phase 4 work and are not claimed here.

See `traceability.md`, `defect-register.md`, `browser-acceptance.md` and the ranking ADR for exact evidence.
