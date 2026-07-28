# Load and independent security-assessment runbook

## Safe capacity probe

`probe_http_capacity` is a bounded, GET-only probe. It refuses remote targets
unless the operator supplies both `--allow-remote` and the exact parsed hostname,
rejects credentials in URLs, does not follow redirects, caps execution at 10,000
requests and 100 concurrent workers, and exits non-zero when the configured
failure-rate or p95 threshold is exceeded.

Local tool validation performed on 2026-07-28:

```powershell
.\venv\Scripts\python.exe manage.py probe_http_capacity `
  --base-url http://127.0.0.1:8001 `
  --path /health/live/ --path / `
  --requests 100 --concurrency 10 `
  --timeout-seconds 5 --max-failure-rate 0 --max-p95-ms 2000
```

Result: 100/100 HTTP 200 responses, zero failures, 31.25 requests/second and
1034.62 ms p95. These numbers validate the tool and selected paths only. They
were produced by Django's Windows development server with SQLite and are **not**
production-capacity evidence or a hosting recommendation.

## Staging load procedure

1. Obtain written authorization for the exact staging hostname, time window,
   source IP, maximum concurrency and named stop authority.
2. Scale staging PostgreSQL and all application resources to the intended
   production sizes. Use synthetic catalog, accounts and orders only.
3. Record baseline CPU, memory, database storage/connections, Key Value
   memory/connections, queue depth and error rate.
4. Run read-only catalog probes in gradual steps. Example only—the client must
   approve the actual workload model:

   ```powershell
   .\venv\Scripts\python.exe manage.py probe_http_capacity `
     --base-url https://emporium-plug-ke-staging-web.onrender.com `
     --expected-host emporium-plug-ke-staging-web.onrender.com --allow-remote `
     --path /health/live/ --path / --path /sitemap.xml `
     --requests 1000 --concurrency 25 `
     --max-failure-rate 0.005 --max-p95-ms 2000
   ```

5. Exercise checkout, payment callback and POS workloads only with a separately
   reviewed stateful test plan. The GET-only probe deliberately cannot create
   orders or payments. Never point a load generator at Daraja or a live payment
   number.
6. Stop immediately on data-integrity errors, sustained 5xx responses, resource
   exhaustion, queue growth without recovery or any effect outside staging.
7. Reconcile created synthetic orders/payments/inventory, capture graphs and
   logs, and remove the synthetic dataset according to the test-data procedure.
8. Record p50/p95/p99, throughput, failures, saturation point, recovery time,
   Git revision, resource sizes and the accepted peak-business workload.

No capacity percentage or maximum shopper count may be claimed before this
staging exercise and client workload decision exist.

## Independent penetration assessment

The assessor must be independent of the implementation and receive a written
rules-of-engagement document containing:

- exact staging domains/IPs, dates, contacts and emergency stop process;
- synthetic accounts for every role and branch;
- explicit authorization for authentication, authorization/IDOR, session/CSRF,
  injection, XSS, file upload, webhook, rate-limit, privacy and business-logic
  testing;
- prohibited activity: production access, real payments/customer data, social
  engineering, destructive denial of service, persistence, data exfiltration or
  contacting real customers/providers; and
- severity model, evidence handling, encryption, retention/deletion, retest and
  disclosure requirements.

The assessor should cover OWASP web/API risks plus this system's critical abuse
cases: cross-branch access, manager-approval bypass, duplicate callbacks,
amount/reference mismatch, stock restoration twice, coupon concurrency, guest
tracking-token exposure, pickup-code guessing, staff impersonation and unsafe
uploads. Findings must be triaged, fixed and independently retested. A local
Bandit/dependency scan is useful evidence but is not a penetration test.

## Automated security checks

CI installs the pinned tools in `requirements-audit.txt` and runs:

```powershell
.\venv\Scripts\python.exe -m pip_audit -r requirements.txt --progress-spinner off
.\venv\Scripts\python.exe -m bandit -r apps config -ll -q
npm.cmd audit --omit=dev --audit-level=moderate
```

Bandit currently reports zero medium/high findings. The JSON-LD serializer's
necessary `mark_safe` use has a narrow scanner suppression backed by an
adversarial closing-script regression test. Dependency audits transmit package
names and versions—not source or secrets—to their advisory services and require
network availability.

Item 10 remains externally incomplete until production-sized staging load and
an independent penetration test/retest have accepted evidence.
