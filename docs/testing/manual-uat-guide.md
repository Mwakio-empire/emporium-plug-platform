# Manual acceptance test guide

## Purpose and release boundary

This guide is the client's repeatable manual acceptance procedure for Emporium
Plug. Complete it before importing live business data or approving production.
It supplements automated tests; it does not replace concurrency, security,
provider or backup tests.

Testing is divided into four gates:

1. **Local browser UAT** — usability and business journeys using synthetic data.
2. **Staging acceptance** — PostgreSQL, Redis, Celery, HTTPS and sandbox providers.
3. **Migration rehearsal** — copy sanitized/source-shaped data into an isolated
   staging database, validate it, then discard it.
4. **Production cutover** — performed only after gates 1–3 pass and the client
   signs the release decision.

Never use live customer data, production M-Pesa credentials, real OTPs or a
real charge during gates 1 and 2. Do not alter audit, payment or stock rows in
Django Admin to make a failed test appear successful.

## People and responsibilities

| Responsibility | Recommended owner |
|---|---|
| Business acceptance and final go/no-go | Client owner/Super Admin |
| Storefront and customer journeys | Client owner plus one independent tester |
| S18 POS and pickup | S18 manager/cashier |
| B03 POS and stock | B03 manager/cashier |
| OTC intake and transfer dispatch | OTC inventory manager |
| Delivery and rider workflow | Operations manager plus test rider |
| Technical evidence and defect triage | Lead engineer |
| M-Pesa reconciliation | Authorized finance/manager representative |

One person should perform the action and another should verify money, stock and
audit evidence for financial or inventory tests.

## Evidence rules

Copy `manual-uat-results-template.md` for each test cycle. For every case record:

- build/commit identifier and environment;
- tester, date/time and role;
- browser/device and branch;
- test case ID;
- exact inputs, excluding passwords, OTPs and payment secrets;
- expected and actual result;
- generated order/payment/transfer reference;
- before/after stock and money totals;
- screenshot or screen recording path;
- Pass, Fail, Blocked or Not Applicable;
- defect ID and retest result.

Mask phone numbers except the last four digits. Do not capture passwords,
manager re-authentication credentials, OTPs, signed tracking tokens, M-Pesa
passkeys, bearer tokens or full customer messages.

## Gate 0 — prepare a safe local test environment

### 0.1 Preserve the current database

1. Stop the Django server and any Celery processes.
2. Record the current project revision or copy the project status into the test
   record.
3. Make a recoverable copy of the local development database before inserting
   UAT data. Do not overwrite the only copy.
4. Confirm `.env` is excluded from source control and do not paste it into the
   results document.
5. Confirm `ENVIRONMENT=development`, `DEBUG=True`,
   `NOTIFICATION_PROVIDER=console`, `MPESA_ENVIRONMENT=sandbox` and
   `BACKUP_ENABLED=False` for local browser testing.
6. Either run Redis locally or set `LOCAL_CACHE_ONLY=True`. Local-cache mode is
   suitable for browser UAT but cannot prove cross-process Celery behavior.

### 0.2 Establish the automated baseline

Run from `C:\Users\hp\dynamic_retail_system`:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe -m compileall -q apps config
.\venv\Scripts\python.exe -m pip check
npm.cmd run build
```

Expected baseline:

- Django reports no issues.
- No model changes require a migration.
- The complete suite passes; the known PostgreSQL-only concurrency test may be
  skipped locally.
- Python compilation, dependency consistency and frontend build pass.

Stop if any new failure appears. Do not start manual testing on a known-broken
build.

### 0.3 Start the application

```powershell
.\venv\Scripts\python.exe manage.py migrate --noinput
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/` in a normal browser window. Use a private window
for guest journeys and separate browser profiles for customer, cashier,
manager and rider sessions to avoid role/session contamination.

### 0.4 Test-data set

Use obviously synthetic names and unused test phone numbers. Create or verify:

**Branches**

- OTC — receiving/source branch.
- Gaberone Plaza S18 — ordinary pickup location.
- Gaberone Plaza B03 — second plaza shop.

The client confirmed the official label is `B03` with a zero.

**Users**

- one Super Admin;
- one Branch Manager for each branch;
- one Inventory Manager at OTC;
- one cashier/Staff user per branch;
- one S18 Staff user with a Rider Profile;
- two verified customers;
- one inactive/locked test account.

Create ordinary staff through `/accounts/staff/invite/` during the relevant
test. Staff, inventory managers and branch managers must have a branch;
customers and Super Admin must not.

**Catalog and stock**

- one simple non-clothing product eligible for seven-day returns;
- one clothing/size/colour product with at least two variants and support-only
  return wording;
- one product with gallery image and structured specifications;
- one out-of-stock item;
- one low-stock item;
- one inactive/hidden product;
- sufficient stock at OTC for intake/transfer tests;
- known opening balances at S18 and B03.

Record the opening on-hand, reserved, in-transit and damaged quantities for
every product used in testing.

**Commerce configuration**

- at least one Kenya delivery zone and fee;
- one future S18 pickup slot and one expired slot;
- one valid percentage coupon and one fixed coupon;
- expired, exhausted and minimum-spend coupon cases;
- one available S18 rider and one offline/busy rider.

## Gate 1 — local browser UAT

Run cases in order because later cases use records created earlier. Repeat the
responsive customer journeys at approximately 390 × 844 and at desktop width.
Check the browser console after each section; unexpected JavaScript errors fail
the case.

### A. Public storefront and branding

| ID | Steps | Expected result |
|---|---|---|
| UAT-STO-01 | Open `/`; inspect header, logo, hero, product cards and footer. | Original Emporium Plug logo remains recognizable; orange/blue theme is consistent; phone/WhatsApp details are readable; no internal “engine/matrix/node” language. |
| UAT-STO-02 | Use category navigation, nested categories, branch, price and availability filters. | Results match every selected filter; inactive products never appear; empty results explain what to do next. |
| UAT-STO-03 | Search by full name, partial name and SKU; search for nonsense. | Relevant visible products appear; unknown search produces a useful empty state without an error. |
| UAT-STO-04 | Sort by newest, price ascending/descending and best selling. | Ordering changes correctly without corrupting the cart or replacing unrelated page content. |
| UAT-STO-05 | Open simple and variant product pages. Select size/colour where applicable; confirm there is no customer branch selector. | Gallery, description, specifications, variant price, company-wide stock, quantity limit, reviews and related products are correct. |
| UAT-STO-06 | Attempt to add an out-of-stock item, too many units and a variant product without selecting a variant. | Each action is rejected with a human-readable message; cart and stock remain unchanged. |
| UAT-STO-07 | Open and close the cart with mouse and keyboard; press Escape. | Focus enters the dialog, Escape closes it and focus returns to the trigger; no horizontal overflow. |
| UAT-STO-08 | Open `/sitemap.xml`, `/robots.txt`, inspect page title/meta/canonical and image alt text. | Files load; public product metadata is meaningful; hidden products are not promoted. |
| UAT-STO-09 | Activate “Order via WhatsApp”. | It opens `+254116153335` with an assisted-order message. It does not reserve stock or create an order. |

### B. Registration, login and account security

| ID | Steps | Expected result |
|---|---|---|
| UAT-AUTH-01 | Register a new customer with Kenyan phone and optional email at `/accounts/signup/`; verify OTP. | Phone is normalized, account activates once, expired/reused OTP is rejected and no OTP appears in UI logs. |
| UAT-AUTH-02 | Request OTP resend repeatedly. | Cooldown/rate limit is enforced and old codes cannot be reused. |
| UAT-AUTH-03 | Log in/out as customer and attempt an incorrect password repeatedly. | Correct login works; logout invalidates the session; throttling/lockout appears without revealing whether another identity exists. |
| UAT-AUTH-04 | Use `/accounts/forgot-password/` and `/accounts/reset-password/`. | Reset requires the proper proof, expires, cannot be replayed and invalidates earlier credentials/tokens as designed. |
| UAT-AUTH-05 | As Super Admin/manager, open `/accounts/staff/invite/`, create branch staff and activate the invite. | Role/branch rules are enforced; mandatory staff OTP occurs; customer cannot create staff. |
| UAT-AUTH-06 | Use an S18 staff account to open B03/OTC operational records by changing a URL or form identifier. | Access is denied; no cross-branch names, totals or object details leak. |
| UAT-AUTH-07 | Attempt a manager-controlled discount/void with wrong password, then correct full manager password. | Wrong password fails and is audited; valid authorized manager approval succeeds; password is never displayed or logged. |

### C. Cart and checkout

Use a private window for guest tests and a customer profile for authenticated
tests. Before every case record stock and clear the cart.

| ID | Steps | Expected result |
|---|---|---|
| UAT-CHK-01 | Add simple and variant products, change quantity, remove an item and refresh/reopen the browser without selecting a branch. | Quantities and totals are correct; the guest/customer cart persists; one internal branch fulfils the complete basket and no branch selector is shown. |
| UAT-CHK-02 | Add as guest, then log in with an existing customer cart. | Merge is deterministic, respects stock limits and does not duplicate lines. |
| UAT-CHK-03 | Open `/orders/checkout/` with an empty cart. | Checkout is blocked with a useful return-to-shopping action. |
| UAT-CHK-04 | Open checkout with products in the cart. Confirm S18 pickup is selected by default and no public delivery selector is present. Open “Arrange on WhatsApp”. | WhatsApp targets 0116 153 335 and pre-fills the cart items, quantities, subtotal and request to confirm destination, transport fee, final total and expected arrival before payment. Opening WhatsApp does not create an order or reserve stock. |
| UAT-CHK-05 | Keep the selected S18 pickup method, choose an active pickup arrangement, choose cash on collection and submit after accepting the confirmation. | Pickup fee remains KES 0; explicit confirmation is required; one pickup order points to S18 and receives protected tracking access. |
| UAT-CHK-06 | Attempt an expired/inactive pickup arrangement, invalid phone, expired coupon, exhausted coupon, below-minimum coupon and an invented coupon code. Also send a forged `ONLINE_DELIVERY` request through an API client. | The page/API explains or safely rejects each invalid value; public delivery is rejected with the WhatsApp-assisted direction; no order, payment or stock movement is created. |
| UAT-CHK-07 | Apply valid fixed and percentage coupons separately, then edit each code and reapply an invalid value. | The page explicitly confirms a valid coupon and saving; discount and final payable amount are exact; stale success feedback clears and confirmation resets after a price-affecting change. |
| UAT-CHK-08 | Change a product price or stock in another authorized session after cart review, then submit. | Checkout detects the change, requires a new review and never sells unavailable stock. |
| UAT-CHK-09 | Complete a guest order; open tracking in the protected link, a second browser and with an altered/expired token. | Valid access shows only that order; altered/expired/missing access cannot reveal it or enumerate other orders. |
| UAT-CHK-10 | Download the authorized receipt PDF. | Correct order, items, totals, branch and payment state render; another customer cannot download it. |
| UAT-CHK-11 | Open the storefront and checkout on a 390-pixel-wide phone and on desktop. Inspect the header, browser tab, selected S18 card and “Send to my town” WhatsApp card. | The header uses an accessible cart icon with quantity badge; the favicon uses the trolley emblem from the approved Emporium Plug logo; both fulfilment cards stack cleanly; no horizontal page overflow or clipped controls occur. |

Do not attempt a real STK Push locally. M-Pesa cases belong to Gate 2.

### D. Walk-in POS and shifts

Use `/pos-desk/` with a branch Staff account.

| ID | Steps | Expected result |
|---|---|---|
| UAT-POS-01 | Attempt a sale without an open shift, then open a shift with recorded opening cash. | Sale is blocked before opening; shift records cashier, branch, time and opening cash. |
| UAT-POS-02 | Search by product name/SKU, choose variant, add/remove quantities. | Only the cashier's branch stock appears; cart/customer display shows identical items and totals. |
| UAT-POS-03 | Complete a cash sale with amount received greater than total. | Full price is populated, explicit placement is required, change is exact, one receipt/order/stock deduction is created and shift totals increase once. |
| UAT-POS-04 | Attempt insufficient cash and duplicate submission. | Insufficient tender is rejected; duplicate order/payment/stock movement is not created. |
| UAT-POS-05 | Apply a discount with cashier credentials, wrong manager credentials, then correct manager credentials and reason. | Unauthorized attempts fail; successful approval records manager, cashier, branch, reason and amount. |
| UAT-POS-06 | Complete a Paybill/manual-reference sale. | Typed reference alone does not prove payment; authorized manual confirmation and reason are required. |
| UAT-POS-07 | Void the completed sale at `/pos-desk/void/<order-number>/`. Repeat the request. | Original sale remains immutable; reversal and manager reason are recorded; stock restores exactly once; second void is rejected/idempotent. |
| UAT-POS-08 | Open `/pos-desk/customer-display/` on a second screen during cart changes. | Customer display mirrors products and total without exposing staff controls or unrelated data. |
| UAT-POS-09 | Close shift with exact expected cash; repeat with a variance and submit manager verification. | Exact close reconciles; variance is visible, explained and escalated according to threshold; manager decision is audited. |

### E. Inventory intake, transfers and counts

Use `/inventory/workspace/`. Keep the opening stock worksheet visible.

| ID | Steps | Expected result |
|---|---|---|
| UAT-INV-01 | As OTC Inventory Manager, record supplier intake with multiple lines. | OTC on-hand increases by exact quantities; one immutable RESTOCK audit movement per line records actor/reference. |
| UAT-INV-02 | Record correction, damage and theft adjustments with reasons. | Reason/note are mandatory; stock buckets change correctly; branch staff cannot perform unauthorized adjustment. |
| UAT-INV-03 | Request OTC → S18 transfer, approve and dispatch. | Before dispatch stock remains at OTC; after dispatch it leaves OTC availability and exists only in transit—not at both branches. |
| UAT-INV-04 | Receive the complete transfer at S18. | In-transit decreases and S18 on-hand increases once; history records requester, approver, dispatcher and receiver. |
| UAT-INV-05 | Repeat with partial receipt, then receive remainder. | Received/in-transit quantities reconcile throughout; total received cannot exceed dispatched quantity. |
| UAT-INV-06 | Test rejection before dispatch and cancellation where permitted. | Valid transition succeeds with reason; invalid/late cancellation is rejected; stock remains correct. |
| UAT-INV-07 | Attempt cross-branch approval/receipt with the wrong branch manager. | Access is denied without record leakage or mutation. |
| UAT-INV-08 | Start a stock count, enter exact quantities and complete it. Repeat with a discrepancy. | Exact count closes cleanly; discrepancy requires explanation and creates correction/audit evidence exactly once. |
| UAT-INV-09 | Reduce stock to the low-stock threshold and repeat the triggering action. | Alert is generated without repeated notification spam for the same unresolved condition. |

### F. Packing, pickup, rider delivery and disputes

Use `/api/logistics/workspace/` for operations and the customer tracking page
for customer-visible status.

| ID | Steps | Expected result |
|---|---|---|
| UAT-FUL-01 | Start packing a paid/approved pickup order; attempt completion before checking every line. | Premature completion fails; each line records the staff actor; completed checklist moves order to packed. |
| UAT-FUL-02 | Mark pickup ready. | Customer sees S18 collection location, pickup code flow and deadline two working days later; Saturday counts and Sunday is skipped. |
| UAT-FUL-03 | Enter wrong pickup code repeatedly, then valid code. | Attempts are limited; wrong code reveals nothing; valid code collects once and records actor/time. |
| UAT-FUL-04 | Attempt collection from B03/OTC without authorized redirection. | Normal pickup remains S18; unauthorized redirection is impossible. |
| UAT-FUL-05 | Pack a delivery and assign an available same-branch rider. Attempt offline, busy, other-branch and concurrent duplicate assignment. | Only available same-branch rider succeeds and becomes busy; one assignment exists. |
| UAT-FUL-06 | As rider, use `/api/logistics/my-deliveries/` and progress Assigned → Picked Up → Out for Delivery → Delivered. | Valid transitions succeed in order; skipped/backward transitions fail; customer timeline updates chronologically. |
| UAT-FUL-07 | Customer confirms delivery, then run a separate delivery-dispute case. | Confirmation closes the intended journey; dispute enters management escalation and cannot be silently overwritten. |
| UAT-FUL-08 | Let a synthetic pickup expire using the controlled staging task/test clock. | Order cancels under approved rule, reservation releases exactly once and reminder/expiry attempts are recorded. Do not alter the live system clock. |

### G. Promotions, reviews and returns

| ID | Steps | Expected result |
|---|---|---|
| UAT-MKT-01 | Redeem valid coupon up to per-customer/global limit; try once more. | Each successful order consumes one redemption atomically; excess use fails without changing totals. |
| UAT-MKT-02 | Attempt review without purchase, then as verified purchaser. | Non-purchaser is rejected; purchaser submits once and sees awaiting moderation. |
| UAT-MKT-03 | Manager opens `/marketing/operations/`, rejects/approves reviews with reason. | Queue is branch/role scoped; decision and reason are audited; customer privacy is preserved. |
| UAT-MKT-04 | Within seven days request return for eligible non-clothing item and a partial quantity. | Valid quantity is accepted once; more-than-purchased and duplicate quantities are rejected. |
| UAT-MKT-05 | Try clothing/support-only and expired-window self-service returns. | Self-service control is absent/rejected with support wording; no unsupported refund promise appears. |
| UAT-MKT-06 | Manager approve as sellable, damaged and quarantined in separate cases. | Correct stock bucket changes once; refund stays pending manual unless a real reconciled refund exists. |
| UAT-MKT-07 | Reject a return with reason. | Customer sees status; stock and payment do not change; audit trail remains. |

### H. Reports and operational reconciliation

Use `/management/reports/` and compare the UI/CSV with the orders, payments,
stock movements, shifts and returns produced above.

| ID | Steps | Expected result |
|---|---|---|
| UAT-RPT-01 | Run today/week/month/custom reports in Africa/Nairobi timezone. | Boundaries are correct and invalid/reversed/overlong ranges fail clearly. |
| UAT-RPT-02 | Compare all-branch, OTC, S18 and B03 totals. | Branch totals add to permitted all-branch totals; branch manager sees only authorized branch. |
| UAT-RPT-03 | Reconcile revenue to recognized order statuses and payment amounts. | Pending, failed, cancelled and voided amounts are treated exactly as the displayed revenue definition states. |
| UAT-RPT-04 | Reconcile payment method, channel, staff sales, discounts, voids, manual confirmations and shift variance sections. | Counts and money equal source transactions with no double counting. |
| UAT-RPT-05 | Reconcile current stock and movement report to opening stock plus every intake/sale/transfer/return/void. | On-hand, reserved, in-transit and damaged balances match the physical worksheet. |
| UAT-RPT-06 | Export CSV for selected period/branch. | Export matches visible scope, handles special characters safely and contains no unauthorized branch/customer data. |

### I. Notifications and privacy/security surfaces

| ID | Steps | Expected result |
|---|---|---|
| UAT-OPS-01 | Open `/notifications/operations/` as manager, Super Admin and unauthorized customer. | Authorized scope is enforced; recipients are masked; message body/secrets are absent; customer is denied. |
| UAT-OPS-02 | Resolve a failed notification with too-short then meaningful evidence. | Short evidence fails; valid evidence records resolver/time/note and removes item from active queue. |
| UAT-OPS-03 | Open `/accounts/privacy/`, submit `/accounts/privacy/request/`, export own data. | Notice clearly identifies pre-launch/legal-review status; request is recorded; export requires recent authentication and contains only that customer. |
| UAT-OPS-04 | Attempt another customer's order, receipt, return, privacy export and branch report by changing IDs/URLs. | Every request is denied without confirming whether the target exists. |
| UAT-OPS-05 | Enter HTML/script-like text into search, name, reason, review and notes. | Content is escaped; no script executes; CSP/browser console shows no unexpected violation caused by application code. |
| UAT-OPS-06 | Test keyboard-only navigation, visible focus, labels/errors and zoom to 200%. | Critical journeys remain operable and readable without mouse or horizontal clipping. |

## Gate 2 — staging and provider acceptance

Gate 2 starts only after Gate 1 has no open Critical/High defect. Deploy
`render.staging.yaml` with synthetic data and separate credentials.

### Staging infrastructure checklist

1. Confirm every service is in Frankfurt and has a staging-prefixed name.
2. Confirm `/health/live/` and `/health/ready/` return HTTP 200. After Beat and
   a worker have completed the one-minute heartbeat task, confirm
   `/health/operations/` also returns HTTP 200.
3. Confirm HTTPS redirect, secure cookies, allowed host and CSRF origin.
4. Confirm web, worker and exactly one Beat process are healthy.
5. Confirm PostgreSQL and Key Value use private internal connection URLs.
6. Confirm migrations complete once and static assets load.
7. Confirm logs contain request IDs but no full phone, OTP, tracking token,
   password or provider secret.
8. Configure Sentry staging environment with default PII disabled and trigger
   the authorized diagnostic once.
9. Configure uptime, readiness, worker, Beat, database and Redis alerts and
   prove each alert/recovery path.

### M-Pesa sandbox

Follow `docs/phase-5/manual-certification-runbook.md` and record the supplied
results template. At minimum prove success, cancellation, timeout/provider
rejection, delayed and duplicate callback, unknown checkout ID, amount/reference
mismatch, bounded polling and authorized manual confirmation.

For every scenario reconcile all four records:

1. provider/sandbox outcome;
2. payment state and exact amount;
3. order status history;
4. reservation/stock audit movement.

Any disagreement is a release blocker. Never “fix” the result directly in the
database.

### PostgreSQL concurrency and idempotency

1. Run the complete automated suite against staging PostgreSQL, including the
   locally skipped locking test.
2. From two browser sessions submit purchase of the final unit simultaneously.
3. Submit the same checkout idempotency key twice.
4. Submit concurrent transfer approval/receipt and rider assignment attempts.
5. Replay the same sanitized payment callback.
6. Confirm only one successful mutation, no negative available stock and one
   appropriate audit movement.

### Background processing

1. Stop the worker, create a safe notification task, restart it and confirm the
   task processes once.
2. Force a safe provider failure and confirm bounded retry/backoff and one
   durable notification attempt chain.
3. Confirm Beat runs scheduled expiry/poll/report tasks once per schedule.
4. Confirm notification failure does not roll back a committed order or
   fulfilment transition.

### Backup, restore, security and load

1. Prove managed PostgreSQL point-in-time restore into a new isolated database.
2. If off-site backup is enabled, run the encrypted `pg_dump` and restore
   procedure in `docs/phase-13/backup-restore.md`.
3. Reconcile restored row counts and sample orders, payments, stock/audit logs.
4. Scale staging PostgreSQL to Basic-1gb before representative load testing.
5. Run catalog, checkout, callback and POS load profiles; record p50/p95/p99,
   error rate, memory, CPU, DB connections and queue depth.
6. Run the external security assessment and close all Critical/High findings.
7. Measure storefront and checkout latency from a Nairobi connection; revisit
   the Frankfurt decision if results breach the accepted target.

## Gate 3 — data-migration rehearsal

Do not start this gate until Gates 1 and 2 pass.

1. Freeze and inventory the proposed source data: branches, staff, customers,
   products, variants, stock, open orders, payments, transfers and promotions.
2. Define field mappings, normalization rules and rejected-row handling. Never
   silently guess branch, phone, product variant, payment or stock ownership.
3. Confirm the production branch seed uses the client-approved `B03` spelling.
4. Re-run `audit_identity_collisions`; Super Admin owns the previously confirmed
   shared phone identity and the other account must use its different verified
   number.
5. Take source and staging backups and record checksums.
6. Import into an isolated restored/staging database—not production.
7. Reconcile counts and monetary totals by entity and branch.
8. Reconcile every branch's opening stock by product/variant and state bucket.
9. Sample at least ten records from each entity and every exceptional/rejected
   row.
10. Repeat the critical customer purchase, POS, transfer, fulfilment, return and
    report journeys against migrated data.
11. Time the rehearsal and document rollback steps.
12. Destroy or anonymize the rehearsal data according to the approved handling
    procedure.

Migration passes only when the import is repeatable, reconciliation differences
are zero or formally explained, rejected rows are resolved, and rollback has
been demonstrated.

## Final go/no-go gate before production migration

Production migration is **No-Go** if any of the following is true:

- any Critical or High defect is open;
- the full automated suite or a critical manual journey fails;
- stock, payment, shift or report totals do not reconcile;
- duplicate callbacks/submissions create duplicate financial or stock effects;
- PostgreSQL final-unit concurrency is unproven;
- backup restore has not succeeded;
- monitoring/alerting is not active;
- privacy/controller, cross-border-processing or provider decisions remain
  unapproved;
- M-Pesa sandbox certification is incomplete;
- client UAT sign-off and explicit production-payment authorization are absent.

When all gates pass, archive the completed test record, defect register,
screenshots, provider evidence, reconciliation workbook, backup/restore report
and signed go-live decision together with the release identifier.
