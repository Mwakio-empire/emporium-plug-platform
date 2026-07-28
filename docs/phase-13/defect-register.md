# Phase 13 defect register

| ID | Severity | State | Evidence/impact | Resolution |
|---|---|---|---|---|
| PROD-001 | Critical | Corrected | No production HTTP server or deploy topology | Pinned Gunicorn and reviewable Render Blueprint |
| PROD-002 | Critical | Corrected | `dumpdata` JSON in local/media storage was represented as backup | Replaced with PostgreSQL custom-format encrypted off-site backup; no local fallback |
| PROD-003 | High | Corrected | No liveness/readiness endpoints | Separate process and DB/cache dependency endpoints with failure tests |
| PROD-004 | High | Corrected | Static files used basic storage and production `collectstatic` failed through Cloudinary's legacy override | WhiteNoise hashed/compressed storage; removed unused override app; production static build passes |
| PROD-005 | High | Corrected | Production origin/proxy/media settings could be incomplete | HTTPS origin/site, proxy and Cloudinary fail-fast gates |
| PROD-006 | Medium | Corrected | Logs lacked stable structure/correlation | JSON production formatter and safe request IDs |
| PROD-007 | High | External gate — funding | No managed staging/production services currently provisioned. The private GitHub repository and staging Blueprint are ready, but on 2026-07-28 Render required a valid payment method and infrastructure funding was unavailable. | Fund the client-owned Render account, review the live Blueprint estimate before applying it, then provision and verify staging. Do not treat local or free-tier-only checks as staging proof. |
| PROD-008 | Critical gate | Implemented locally; external gate | Native backup creation and uploaded-archive verification are locally tested, but no managed PITR or logical restore has succeeded. | Fund managed staging, enable PITR, provision approved off-site storage, then complete and measure both restore exercises before launch. |
| PROD-009 | High | Implemented locally; external gate | Liveness, readiness and combined Beat/broker/worker freshness are testable, but no external monitor, Render notification recipient or Sentry alert has delivered a real staging alert. | Fund staging, configure named recipients, then execute and retain every failure/recovery drill in `monitoring-runbook.md`. |
| PROD-010 | High | Implemented locally; external gate | A bounded capacity tool and CI security scans now exist, but development-server numbers are not capacity evidence and no independent assessor has tested staging. | Fund production-sized staging, approve the workload/rules of engagement, execute load testing, remediate findings and obtain an independent penetration retest. |
| PROD-011 | Medium | Resolved | Frankfurt and the cost-conscious initial sizes were approved on 2026-07-26 | Measure Nairobi-to-staging latency and retain the documented cross-border-data caveat |
| PROD-012 | Medium | Open | Render Blueprint has not been validated by Render CLI/API | Validate immediately before sync; no deployment was attempted here |
| PROD-013 | High | Corrected | Staging could boot only by claiming privacy approval and enabling a non-console notification provider | Separate staging/production gates and isolated staging Blueprint; production gates remain strict |
| PROD-014 | High | External gate | Workspace has no usable Git remote and no authenticated Render CLI/API session | Connect the client-owned repository and Render account before Blueprint sync |
