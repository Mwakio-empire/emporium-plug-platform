# Testing guide

## Local automated gate

Run from the repository root with test-safe provider configuration:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe -m compileall -q apps config
.\venv\Scripts\python.exe manage.py test --verbosity 1
.\venv\Scripts\python.exe -m pip check
node --check static/orders/checkout.js
npm.cmd run build
```

Expected negative tests deliberately log 400/401/403/404 responses and simulated provider/broker failures. The command exit code and final test summary decide pass/fail.

## Test layers

| Layer | Evidence |
|---|---|
| Models/constraints | Application `tests.py` and `tests/` modules, including exact-one-item and financial constraints. |
| Services/transactions | Inventory, checkout, payment, fulfilment, promotions and reconciliation suites. |
| Authorization | Role, object ownership and cross-branch denial tests. |
| API/views/templates | DRF and Django client tests. |
| Browser journeys | Phase browser-acceptance records and manual UAT. |
| Provider integration | Separate Daraja/Africa's Talking sandbox execution only. |
| PostgreSQL concurrency | Staging PostgreSQL; the SQLite `select_for_update` test is expected to skip locally. |
| Recovery/load/security | Controlled staging exercises with retained evidence. |

## Manual acceptance

Use the [manual UAT guide](../testing/manual-uat-guide.md) and copy the [results template](../testing/manual-uat-results-template.md) for each release candidate. Use synthetic customers and sandbox payments. Record tester, environment, build/revision, evidence and defect reference.

Do not perform a real STK Push, send a real customer notification, restore over an active database or use production data without written authorization.

## External suites

- Daraja: follow [payment certification](../phase-5/manual-certification-runbook.md).
- PostgreSQL concurrency: follow [Phase 5 concurrency](../phase-5/postgresql-concurrency.md).
- Deployment/recovery: follow [deployment](../phase-13/deployment-runbook.md) and [backup/restore](../phase-13/backup-restore.md).
- Capacity/security: use the bounded probe and independent-assessor rules in the [load/security runbook](../phase-13/load-security-runbook.md). Local scan results never replace a staging penetration test.
- Accessibility and responsive UI: execute critical journeys with keyboard, 390-pixel mobile and desktop viewports; retain screenshots and console results.

## Failure handling

Do not weaken assertions to make a release green. Reproduce, classify severity/business impact, fix the smallest coherent scope, rerun the focused test, then rerun this full gate. A flaky financial, inventory or authorization test is a release blocker until its cause is understood.
