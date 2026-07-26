# Phase 3 Requirements Traceability

| Requirement | Current evidence | State |
|---|---|---|
| Responsive homepage | Responsive layout; 390 x 844 browser inspection found no horizontal overflow | Complete and verified |
| Nested category navigation | Recursive public tree; descendants of hidden ancestors are excluded | Complete and verified |
| Product search | Name, description, SKU and category search | Complete and verified |
| Price/category/availability/branch filters | Combined HTML filters and branch-scoped REST stock | Complete and verified |
| Sort by newest, price and sales | Newest/price/name plus rolling 90-day fulfilled quantities across channels | Complete and verified |
| Main image and gallery | Ordered gallery model, admin inline and required alt text | Complete and verified |
| Description and specifications | Description, weight, dimensions and structured specifications render | Complete and verified |
| Variant selector and price | Variant price, branch stock and sold-out controls | Complete and verified by focused tests |
| Branch-aware availability | Listing, detail, cart, checkout and REST API scoped by branch | Complete and verified |
| Quantity limit | Customer quantity input and server-side stock cap | Complete and verified |
| Reviews | Approved reviews and average rating; customer surname/phone not shown | Complete and verified by view tests |
| Related products | Public, same-category products use the same visibility and branch boundary | Complete and verified |
| Persistent customer cart | Per-customer/per-branch database snapshot with same-branch login merge | Complete and verified |
| Guest cart | Session cart with isolation and fallback tests | Complete and verified |
| Stock/price checkout revalidation | Cart/order services revalidate; comprehensive checkout remains Phase 4 | Implemented; Phase 4 exit evidence required |
| Empty/error/out-of-stock states | Server-rendered listing, detail and cart outcomes | Complete and verified |
| SEO | Titles, descriptions, canonical URLs, JSON-LD, sitemap and robots policy | Complete and verified |
| Accessibility | Labels, fieldsets, headings, skip link, focus styles and browser-verified dialog focus/Escape behavior | Complete and verified for Phase 3 critical journey |
| Mobile responsiveness | Responsive grids and mobile browser inspection | Complete and verified |
| Human customer language | Storefront customer copy reviewed and corrected | Complete and verified for Phase 3 pages |
| Reproducible frontend assets | Pinned lockfile; local Tailwind CSS and HTMX build | Complete and verified |
