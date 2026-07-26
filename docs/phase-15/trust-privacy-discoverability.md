# Trust, privacy and discoverability implementation

Status: implemented and locally verified on 2026-07-26, with the launch decisions below still open.

## Customer-facing trust pages

- `/about/` describes the real Nairobi operation, unified online shop, S18 pickup, assisted town parcels, payment verification and support numbers.
- `/terms/` documents accounts, product information, order acceptance, payments, pickup, town parcels, promotions, returns, reviews, service availability, privacy and Kenyan governing-law intent.
- `/accounts/privacy/` documents implemented data categories, purposes, sources, processors, essential cookies, retention, security, data-subject rights and the reviewed deletion process.
- Legal pages remain explicitly marked pre-launch until the client supplies and approves the controller/legal identity, formal contact, processor record, retention schedule and qualified Kenyan legal review.

## Cookies

The current storefront uses only essential first-party session and CSRF cookies. No advertising pixel, behavioural analytics tag or cross-site marketing cookie was found in the rendered storefront implementation. An “accept all” banner is therefore not implemented because it would imply an optional choice while the session/cart/security service cannot operate without those cookies.

If optional analytics or advertising is introduced, it must remain disabled until the customer receives purpose-specific information and can accept, reject and later withdraw the optional choice. The provider and retention record must be updated at the same time.

## Customer account controls

- `/accounts/profile/` gives signed-in customers a profile page, recent account-linked orders and links to privacy controls.
- Customers may edit low-risk name fields. Verified phone and email changes remain support-assisted until a secure re-verification flow is implemented.
- Account deletion is exposed as a password-confirmed `DELETION` privacy request. It is not an immediate hard delete because order, payment, fraud and audit evidence may still have an approved lawful retention purpose.
- Privacy exports and request outcomes remain audited.

## Search and AI discovery controls

- Dedicated canonical category pages are available at `/category/<slug>/`.
- Public home, category, product and trust URLs are included in `/sitemap.xml`.
- Filter/query pages receive `noindex,follow` to reduce duplicate-index noise.
- Product pages emit server-rendered Product/Offer JSON-LD with price, KES currency, availability, SKU, brand, condition and seller.
- All public pages emit OnlineStore and WebSite JSON-LD, canonical URLs, descriptions and Open Graph metadata.
- `/robots.txt` allows public crawling, blocks internal surfaces and explicitly allows `OAI-SearchBot`.

These controls improve eligibility and machine understanding. They do not guarantee indexing, a rich result, first position, a Google recommendation or a ChatGPT recommendation.

## Launch actions that code cannot complete

1. Deploy to the approved public HTTPS domain and replace every `example.com` setting.
2. Populate unique, accurate names, descriptions, specifications, images and alt text for the real catalog.
3. Verify the domain in Google Search Console, submit the sitemap and inspect representative product URLs.
4. Validate product pages with Google Rich Results Test and resolve production-only findings.
5. Create and verify the Google Business Profile for the real customer-facing location.
6. Configure Google Merchant Center and a maintained product feed if the client wants free shopping listings.
7. Earn genuine local citations, reviews and relevant links; do not buy or manufacture spam links.
8. Monitor indexed pages, product impressions, crawl errors, Core Web Vitals and ChatGPT referral traffic after launch.
9. Approve the legal controller identity, privacy contact, retention schedule, processor list and final legal wording.

## Honest scoring method

Scores must distinguish code readiness from live ranking outcomes:

- Technical crawl and machine-understanding readiness can be scored from the rendered application.
- Actual visibility cannot be scored responsibly before a public domain is indexed and production Search Console/Merchant Center data exists.
- No ethical SEO provider can guarantee first position. Ranking varies by query, location, competition, history, quality, reputation and user intent.
