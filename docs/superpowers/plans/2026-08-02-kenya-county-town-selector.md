# Kenya County and Town Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace delivery-quote free-text county and town inputs with a server-validated 47-county selector, county-dependent Kenyan town selector and explicit unlisted-town fallback.

**Architecture:** `KenyaCounty` remains the county reference and a new `KenyaTown` model stores a maintained KNBS-derived urban-centre baseline. Checkout receives active counties during server rendering, fetches active towns from a public read-only logistics endpoint, and submits identifiers to `DeliveryQuoteService`, which resolves them server-side before writing immutable county/town snapshots to the quote. Custom town text is accepted only through an explicit fallback path.

**Tech Stack:** Python 3, Django 6, Django REST Framework, PostgreSQL/SQLite-compatible migrations, Django templates, vanilla JavaScript, Django TestCase/APITestCase.

## Global Constraints

- Selecting a destination creates only a delivery-quote request; it must not create an order, reserve stock, initiate payment or promise a route.
- Seed the initial town list from the KNBS 2019 Population and Housing Census urban-centre dataset and document the source revision.
- Retain `DeliveryQuoteRequest.county` and `.town` as historical text snapshots.
- Never trust the browser's county/town relationship; validate it again in the service layer.
- A legitimate unlisted destination must remain requestable through an explicit fallback.
- Do not expose route pricing, operators, customer data or internal logistics data through the location endpoint.
- Do not add a third-party JavaScript select dependency.
- Preserve pickup as the default fulfilment method.
- Follow the client's batching instruction: do not commit after each task; create one implementation commit after all verification gates pass.

## File Structure

- Create `apps/logistics/location_services.py`: town-name normalization and destination resolution.
- Create `apps/logistics/migrations/0013_kenyatown.py`: `KenyaTown` schema and constraints.
- Create `apps/logistics/migrations/0014_seed_kenya_towns_2019.py`: frozen KNBS-derived county/town seed rows.
- Create `apps/logistics/tests/test_location_reference.py`: model, seed, API, resolver and import tests.
- Create `apps/logistics/management/commands/import_kenya_towns.py`: validated reference-data maintenance.
- Modify `apps/logistics/models.py`, `admin.py`, `serializers.py`, `views.py`, and `urls.py`.
- Modify delivery-quote service/view/tests, checkout view/template/JavaScript/tests and the relevant operational documentation.

---

### Task 1: Kenya Town Reference Model and Seed Data

**Files:**
- Create: `apps/logistics/migrations/0013_kenyatown.py`
- Create: `apps/logistics/migrations/0014_seed_kenya_towns_2019.py`
- Create: `apps/logistics/tests/test_location_reference.py`
- Modify: `apps/logistics/models.py`

**Interfaces:**
- Produces: `KenyaTown(county, name, normalized_name, is_active, source, source_revision)`.
- Database invariant: unique `(county, normalized_name)`.

- [x] **Step 1: Write failing model and seed-data tests**

Add tests proving case/spacing-equivalent names in one county are rejected, the same name may occur in different counties, and the seeded database has 47 active counties with town coverage.

```python
class KenyaTownModelTests(TestCase):
    def test_normalized_town_name_is_unique_within_county(self):
        county = KenyaCounty.objects.create(code='99', name='Test County')
        KenyaTown.objects.create(county=county, name='  Test   Town  ')
        with self.assertRaises(ValidationError):
            KenyaTown.objects.create(county=county, name='test town')

    def test_reference_data_contains_all_47_counties(self):
        self.assertEqual(KenyaCounty.objects.filter(is_active=True).count(), 47)
        self.assertFalse(
            KenyaCounty.objects.filter(is_active=True, towns__isnull=True).exists()
        )
```

- [x] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\venv\Scripts\python.exe manage.py test logistics.tests.test_location_reference --verbosity 2
```

Expected: import/model failure because `KenyaTown` does not exist.

- [x] **Step 3: Add the model and schema migration**

Normalize names with Unicode NFKC, collapsed whitespace and `casefold()` before validation/save. Reject empty names and control characters. Add an index for `(county, is_active, name)` and a unique database constraint for `(county, normalized_name)`.

```python
class KenyaTown(models.Model):
    county = models.ForeignKey(
        KenyaCounty, on_delete=models.PROTECT, related_name='towns',
    )
    name = models.CharField(max_length=100)
    normalized_name = models.CharField(max_length=100, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    source = models.CharField(max_length=80, default='KNBS')
    source_revision = models.CharField(max_length=40, default='2019-KPHC')

    class Meta:
        ordering = ['county__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['county', 'normalized_name'],
                name='unique_normalized_town_per_county',
            ),
        ]
```

- [x] **Step 4: Freeze and seed the KNBS rows**

Extract county/town pairs from the official KNBS workbook during development, normalize obvious whitespace only, review duplicates, then freeze the reviewed tuples inside migration `0014`. The migration must not download at runtime. Use `source='KNBS'` and `source_revision='2019-KPHC-URBAN-CENTRES'`; reverse migration deletes only that revision.

- [x] **Step 5: Verify the model, seed and migration state**

Run the location test module and `manage.py makemigrations --check --dry-run`. Expected: tests pass and no model drift.

---

### Task 2: Destination Resolver and Public Town Lookup API

**Files:**
- Create: `apps/logistics/location_services.py`
- Modify: `apps/logistics/serializers.py`
- Modify: `apps/logistics/views.py`
- Modify: `apps/logistics/urls.py`
- Modify: `config/settings.py`
- Test: `apps/logistics/tests/test_location_reference.py`

**Interfaces:**
- Produces: `ResolvedTownSelection(county_name: str, town_name: str)`.
- Produces: `TownSelectionService.resolve(*, county_code: str, town_id: int | None, use_custom_town: bool, custom_town: str) -> ResolvedTownSelection`.
- Produces: `GET /api/logistics/towns/?county=<two-digit-code>` returning `[{"id": 1, "name": "Kakamega"}]`.

- [x] **Step 1: Write failing resolver tests**

Cover a valid selected town, explicit custom town, nonexistent/inactive county, inactive town, cross-county town, ambiguous selected-plus-custom input, missing selection, overlong input and control characters.

```python
def test_resolver_rejects_town_from_another_county(self):
    with self.assertRaisesMessage(
        ValidationError, 'Choose a town belonging to the selected county.'
    ):
        TownSelectionService.resolve(
            county_code=self.kakamega.code,
            town_id=self.kisumu_town.pk,
            use_custom_town=False,
            custom_town='',
        )
```

- [x] **Step 2: Run resolver tests and verify RED**

Expected: import failure because `TownSelectionService` is absent.

- [x] **Step 3: Implement the resolver**

Use an immutable dataclass for resolved snapshot names. Query only active reference records. Require exactly one path: selected `town_id`, or `use_custom_town=True` with safe text. Return database names for selected towns and never accept a browser-provided selected-town name.

- [x] **Step 4: Write failing lookup API tests**

Test anonymous access, deterministic ordering, county isolation, inactive exclusion, missing/invalid/inactive county handling, and a response containing only `id` and `name`.

- [x] **Step 5: Run lookup tests and verify RED**

Expected: URL reverse failure for `logistics:towns`.

- [x] **Step 6: Implement the lookup endpoint**

Add a two-field serializer, `AllowAny` API view, `ScopedRateThrottle` with `throttle_scope='location_lookup'`, and `path('towns/', TownListView.as_view(), name='towns')`. Validate the county before querying. Cache only successful results by county and reference-data version.

- [x] **Step 7: Configure and verify throttling**

Add `location_lookup: '120/min'` to the existing throttle-rate mapping. Run the location module and `manage.py check`.

---

### Task 3: Server-Validated Delivery Quote Creation

**Files:**
- Modify: `apps/orders/delivery_quote_services.py`
- Modify: `apps/orders/delivery_quote_views.py`
- Modify: `apps/orders/tests/test_delivery_quotes.py`

**Interfaces:**
- Consumes: `TownSelectionService.resolve(...)`.
- Changes: `DeliveryQuoteService.create_request(..., county_code, town_id=None, use_custom_town=False, custom_town='', ...)`.
- Retains: stored county and town display snapshots.

- [x] **Step 1: Write failing structured-selection quote tests**

Create county/town fixtures. Assert a valid selected town stores canonical names. Add custom-town success plus cross-county, inactive and tampered rejection cases. For every rejection assert no quote, order or inventory reservation is created.

- [x] **Step 2: Run focused tests and verify RED**

```powershell
.\venv\Scripts\python.exe manage.py test orders.tests.test_delivery_quotes.DeliveryQuoteAPITests --verbosity 2
```

Expected: structured payload fails because the current view expects free text.

- [x] **Step 3: Change the service boundary**

Resolve the destination inside `create_request` before writing the quote. Use resolved names for length checks and snapshot fields. Preserve cart, stock, phone, email, transaction and throttle behavior.

- [x] **Step 4: Change API payload mapping**

```python
county_code=request.data.get('county_code'),
town_id=request.data.get('town_id'),
use_custom_town=request.data.get('use_custom_town') is True,
custom_town=request.data.get('custom_town', ''),
```

Do not retain a compatibility path for arbitrary free-text `county` and `town`.

- [x] **Step 5: Verify quote and checkout APIs**

Run delivery-quote, checkout API and online-checkout test modules. Expected: all pass and quote creation has no stock/order side effects.

---

### Task 4: Dependent Checkout Controls

**Files:**
- Modify: `apps/orders/views.py`
- Modify: `templates/orders/checkout.html`
- Modify: `static/orders/checkout.js`
- Modify: `apps/orders/tests/test_checkout_page.py`

**Interfaces:**
- Consumes: active counties and the town lookup endpoint.
- Produces: `county_code`, `town_id`, `use_custom_town`, and `custom_town`.

- [x] **Step 1: Write failing page tests**

Assert active county choices render, inactive counties do not, county/town controls are selects, town starts disabled, the unlisted fallback exists, and pickup remains checked.

- [x] **Step 2: Run page tests and verify RED**

Expected: failure because county and town are free-text inputs.

- [x] **Step 3: Provide active counties**

Query active counties ordered by name in `CheckoutPageView` and expose only `code` and `name` as `delivery_counties`.

- [x] **Step 4: Render accessible controls**

```html
<select id="quote-county" required autocomplete="address-level1">
  <option value="">Select county</option>
  {% for county in delivery_counties %}
    <option value="{{ county.code }}">{{ county.name }}</option>
  {% endfor %}
</select>
<select id="quote-town" required disabled aria-describedby="quote-town-status">
  <option value="">Select a county first</option>
</select>
<p id="quote-town-status" role="status" aria-live="polite"></p>
<div id="quote-custom-town-field" hidden>...</div>
```

The custom input is required only while visible. Preferred collection area remains free text.

- [x] **Step 5: Implement JavaScript state management**

On county change: abort an in-flight request, clear stale town/custom values, disable town, show loading copy, fetch the encoded county, render returned options plus `My town isn't listed`, then enable town. On `__OTHER__`: reveal and require custom town. On ordinary town: hide, clear and unrequire it. A failure must show retry guidance and allow explicit manual fallback without losing the rest of the form.

Update quote completeness and payload functions. Hidden quote controls must be disabled so pickup submission is unaffected.

- [x] **Step 6: Verify page and quote behavior**

Run checkout-page and delivery-quote tests, then `node --check static\orders\checkout.js`. Expected: all pass and JavaScript exits 0.

---

### Task 5: Administration, Import and Documentation

**Files:**
- Modify: `apps/logistics/admin.py`
- Create: `apps/logistics/management/commands/import_kenya_towns.py`
- Modify: `apps/logistics/tests/test_location_reference.py`
- Modify: `docs/business/parcel-to-town-operations.md`
- Modify: `docs/phase-15/api-reference.md`
- Modify: `docs/phase-15/requirements-traceability.md`
- Modify: `docs/testing/manual-uat-guide.md`
- Modify: `docs/phase-15/changelog.md`

**Interfaces:**
- Produces: `python manage.py import_kenya_towns <csv-path> --source-revision <value> [--deactivate-missing]`.
- CSV columns: `county_code,town`.

- [x] **Step 1: Write failing command tests**

Use temporary CSV files to verify idempotent create/update, unknown-county rejection, normalized duplicate rejection, full validation before writes and opt-in deactivation limited to the supplied revision.

- [x] **Step 2: Run command tests and verify RED**

Expected: `Unknown command: import_kenya_towns`.

- [x] **Step 3: Implement atomic import**

Parse UTF-8 CSV with exact headers, normalize every row, validate the entire file before writing, then use one transaction. Require a non-empty revision; never guess counties or move an existing town between counties. Print aggregate counts only.

- [x] **Step 4: Register safe administration**

Add town search, county/active/revision filters, deterministic ordering and `list_select_related=('county',)`. Deactivation is the normal correction path; add no bulk deletion action.

- [x] **Step 5: Update documentation**

Document the endpoint, KNBS baseline, fallback, update command and the limitation that a listed town is not an approved route or quoted fee. Add desktop/mobile manual UAT steps.

- [x] **Step 6: Verify logistics and docs**

Run the logistics tests and `git diff --check`. Expected: all pass with no whitespace errors.

---

### Task 6: Browser Journey and Full Release Verification

**Files:**
- Modify only when a failing test or browser observation requires a scoped correction.

**Interfaces:**
- Consumes the complete feature.
- Produces verification evidence and one final implementation commit.

- [x] **Step 1: Apply and inspect PostgreSQL migrations**

```powershell
.\venv\Scripts\python.exe manage.py migrate --noinput
.\venv\Scripts\python.exe manage.py showmigrations logistics
```

Expected: `0013_kenyatown` and `0014_seed_kenya_towns_2019` are marked `[X]`.

- [x] **Step 2: Exercise desktop and mobile browser journeys**

Verify pickup remains selected; delivery reveals county; town starts disabled; Kakamega loads only its towns; changing to Kisumu clears stale state; keyboard navigation works; fallback becomes required; network failure is recoverable; selected and custom destinations reach the quote page; no order or stock reservation is created.

- [x] **Step 3: Run focused tests**

```powershell
.\venv\Scripts\python.exe manage.py test logistics.tests.test_location_reference orders.tests.test_delivery_quotes orders.tests.test_checkout_page --verbosity 1
```

Expected: all pass.

- [x] **Step 4: Run complete verification**

```powershell
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m compileall -q apps config
node --check static\orders\checkout.js
git diff --check
```

Expected: full suite passes with only documented backend-feature skips, system checks are clean, no migration drift, and syntax/diff checks exit 0.

- [ ] **Step 5: Inspect scope and secrets hygiene**

Confirm `.env`, databases and backups are absent from the staged list. Inspect the patch for credentials and accidental unrelated files.

- [ ] **Step 6: Create one batched implementation commit**

Stage only the feature files listed in this plan and commit with:

```powershell
git commit -m "feat: add Kenya county and town selectors"
```

Do not stage unrelated accumulated changes solely because they are present in the working tree.
