# Delivery Quotes and Controlled Coupon Stacking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add protected, staff-priced parcel quote requests and enforce the approved controlled coupon-stacking policy through one tested checkout calculation.

**Architecture:** `DeliveryQuoteRequest` is a pre-order aggregate containing customer contact data, an informational cart snapshot, SLA/status fields and the staff-published transport terms. `DeliveryQuoteService` owns transitions and business-time calculations; existing checkout creates the real parcel order only through an accepted, unexpired quote and still uses the established atomic inventory service. Promotion eligibility remains centralized in `PromotionService` and receives the order/cart pricing sources explicitly.

**Tech Stack:** Django, Django REST Framework, PostgreSQL, Django templates, vanilla JavaScript, Celery-backed durable notifications, existing session cart and audit services.

## Global Constraints

- Working hours: Monday-Saturday, 08:00-18:00 Africa/Nairobi.
- Response target: 30 working minutes.
- Quote validity: 24 elapsed hours from publication.
- Quote requests never create orders, reserve stock or consume coupons.
- Town-parcel orders require M-Pesa prepayment.
- One coupon per order; wholesale pricing never stacks; flash-sale stacking requires an explicit coupon flag.
- Guest access requires a signed token; a quote reference is not authorization.
- Preserve all existing uncommitted project work.

---

### Task 1: Controlled coupon eligibility and transparent totals

**Files:**
- Modify: `apps/marketing/models.py`
- Modify: `apps/marketing/services.py`
- Modify: `apps/marketing/admin.py`
- Modify: `apps/orders/checkout_views.py`
- Create: `apps/marketing/migrations/0004_coupon_allow_discounted_items.py`
- Test: `apps/marketing/tests.py`
- Test: `apps/orders/tests/test_checkout_api.py`

**Interfaces:**
- Consumes: cart item dictionaries containing `pricing_source`, `regular_price`, `price`, `quantity`.
- Produces: `PromotionService.validate_coupon_preview(..., pricing_sources=())` and coupon field `allow_discounted_items: bool`.

- [ ] Write failing tests proving a default coupon rejects `FLASH_SALE`, an opted-in coupon applies to the reduced subtotal, and both reject `WHOLESALE`.
- [ ] Run `python manage.py test apps.marketing.tests apps.orders.tests.test_checkout_api --verbosity 1` and confirm failures identify missing controlled-stacking behaviour.
- [ ] Add `allow_discounted_items = models.BooleanField(default=False)` and expose it in the audited admin.
- [ ] Centralize pricing-source eligibility in `PromotionService`; call it from both preview and redemption.
- [ ] Return `product_discount_amount` separately from `discount_amount` in checkout preview.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Quote persistence, business hours and protected access

**Files:**
- Modify: `apps/orders/models.py`
- Create: `apps/orders/delivery_quote_access.py`
- Create: `apps/orders/delivery_quote_services.py`
- Create: `apps/orders/migrations/0014_delivery_quote_request_and_closure.py`
- Create: `apps/orders/tests/test_delivery_quotes.py`

**Interfaces:**
- Produces: `DeliveryQuoteRequest`, `DeliveryQuoteClosure`, `DeliveryQuoteService.response_due_at()`, `issue_delivery_quote_token()` and `resolve_delivery_quote_token()`.

- [ ] Write failing model/service tests for 30 working-minute deadlines, Saturday-to-Monday rollover, configured closures, 24-hour publication expiry and invalid transitions.
- [ ] Run the new test module and verify expected failures.
- [ ] Add constrained status, money, contact, snapshot, staff, timing and optional accepted-order fields.
- [ ] Implement signed token access using Django signing with a dedicated salt and maximum age.
- [ ] Implement transition methods using `transaction.atomic()` and `select_for_update()`.
- [ ] Run the new module and migration drift check.

### Task 3: Customer request and status APIs

**Files:**
- Create: `apps/orders/delivery_quote_views.py`
- Modify: `apps/orders/checkout_urls.py`
- Modify: `apps/orders/order_urls.py`
- Modify: `config/settings.py`
- Test: `apps/orders/tests/test_delivery_quotes.py`

**Interfaces:**
- Produces: `POST /api/checkout/delivery-quotes/`, `GET /api/orders/delivery-quotes/<reference>/`, decline and accept endpoints.

- [ ] Write failing API tests for authenticated ownership, guest token access, malformed contact/location data, empty cart, throttling contract, request creation without stock mutation, and protected status reads.
- [ ] Run the API tests and verify failures.
- [ ] Implement request creation from the current cart with normalized phone, validated optional email, informational line snapshots and business response deadline.
- [ ] Implement owner/token resolution shared by status, decline and acceptance endpoints.
- [ ] Add scoped throttle rates for request creation and status/accept actions.
- [ ] Run the API tests and Django checks.

### Task 4: Staff quote workspace and audited publication

**Files:**
- Create: `apps/orders/delivery_quote_staff_views.py`
- Create: `apps/orders/templates/orders/delivery_quote_workspace.html`
- Create: `apps/orders/templates/orders/delivery_quote_detail.html`
- Modify: `apps/orders/urls.py`
- Modify: `apps/logistics/templates/logistics/fulfilment_workspace.html`
- Modify: `apps/orders/admin.py`
- Test: `apps/orders/tests/test_delivery_quotes.py`

**Interfaces:**
- Consumes: `DeliveryQuoteService.start_review()` and `publish()`.
- Produces: branch-scoped oldest-first workspace with overdue highlighting and validated publication form.

- [ ] Write failing permission, branch-isolation, transition and form-validation tests.
- [ ] Run the focused tests and verify failures.
- [ ] Implement staff list/detail views using the existing role helpers and CSRF-protected forms.
- [ ] Queue audit records after successful transitions and expose closure configuration through Django admin.
- [ ] Link the fulfilment workspace to open delivery quotes.
- [ ] Run the focused tests.

### Task 5: Quote-aware checkout and idempotent order acceptance

**Files:**
- Modify: `apps/orders/models.py`
- Modify: `apps/orders/online_services.py`
- Modify: `apps/orders/checkout_views.py`
- Modify: `apps/orders/checkout_access.py`
- Test: `apps/orders/tests/test_delivery_quotes.py`
- Test: `apps/orders/tests/test_online_checkout.py`

**Interfaces:**
- Produces: `DeliveryQuoteService.accept_and_create_order(request, quote, ...) -> Order` and a one-to-one quote/order relationship.

- [ ] Write failing tests proving acceptance revalidates current stock/prices/coupon, requires explicit confirmation after a changed total, creates a prepaid parcel order once, reserves stock once and returns the same order on retries.
- [ ] Run focused tests and verify failures.
- [ ] Add the accepted quote as the only public authorization source for `ONLINE_DELIVERY` checkout and use its fixed transport fee/details.
- [ ] Create order items from validated quote snapshot identities without trusting snapshot prices.
- [ ] Link the accepted order atomically, consume the coupon only once and reject COD.
- [ ] Run delivery quote and online checkout suites.

### Task 6: Customer pages, countdown and WhatsApp escalation

**Files:**
- Modify: `templates/orders/checkout.html`
- Modify: `static/orders/checkout.js`
- Create: `apps/orders/templates/orders/delivery_quote_status.html`
- Create: `static/orders/delivery_quote.js`
- Modify: `apps/orders/views.py`
- Modify: `apps/orders/urls.py`
- Test: `apps/orders/tests/test_delivery_quotes.py`

**Interfaces:**
- Produces: accessible request form/status timeline, deadline countdown, overdue WhatsApp escalation and quote acceptance UI.

- [ ] Write failing rendered-view tests for pickup default, quote form, after-hours copy, secure status shell and overdue fallback.
- [ ] Run view tests and verify failures.
- [ ] Replace the WhatsApp-only town card with a form-driven choice while retaining WhatsApp help.
- [ ] Render separate regular-price value, product savings, coupon savings, transport fee and final total.
- [ ] Implement countdown using server timestamps; never make client time authoritative.
- [ ] Run template/view tests and `node --check` on both JavaScript files.

### Task 7: Durable quote notifications and expiry

**Files:**
- Modify: `apps/notifications/catalog.py`
- Modify: `apps/notifications/tasks.py`
- Modify: `config/celery.py`
- Modify: `docs/phase-11/event-catalog.md`
- Test: `apps/notifications/tests.py`
- Test: `apps/orders/tests/test_delivery_quotes.py`

**Interfaces:**
- Produces: `DELIVERY_QUOTE_READY` event and periodic `expire_delivery_quotes` task.

- [ ] Write failing tests for deduplicated ready notifications, no notification on rollback, safe no-email behaviour and expiry without inventory/coupon mutation.
- [ ] Run focused tests and verify failures.
- [ ] Add SMS/email tasks containing the protected status URL but no sensitive data in logs.
- [ ] Schedule bounded expiry processing and make it idempotent.
- [ ] Run notification and quote tests.

### Task 8: Documentation and release verification

**Files:**
- Modify: `docs/business/store-pickup-and-delivery-policy.md`
- Modify: `docs/business/parcel-to-town-operations.md`
- Modify: `docs/testing/manual-uat-guide.md`
- Modify: `docs/phase-9/quantity-pricing-decision.md`
- Modify: `docs/phase-15/api-reference.md`
- Modify: `docs/phase-15/manager-operations-guide.md`
- Modify: `docs/phase-15/requirements-traceability.md`
- Modify: `docs/phase-15/changelog.md`

- [ ] Update documents to distinguish quote requests from orders and record controlled stacking exactly as implemented.
- [ ] Run focused quote, checkout, marketing and notification tests.
- [ ] Run `python manage.py check` and `python manage.py makemigrations --check --dry-run`.
- [ ] Run the full automated test suite.
- [ ] Browser-test pickup, quote submission, staff publication, overdue WhatsApp and accepted M-Pesa order at mobile and desktop widths.
- [ ] Record manual Daraja sandbox and real notification delivery as external verification gates, not automated successes.
