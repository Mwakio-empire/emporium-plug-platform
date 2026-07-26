# Phase 13 defect register

| ID | Severity | State | Evidence/impact | Resolution |
|---|---|---|---|---|
| PROD-001 | Critical | Corrected | No production HTTP server or deploy topology | Pinned Gunicorn and reviewable Render Blueprint |
| PROD-002 | Critical | Corrected | `dumpdata` JSON in local/media storage was represented as backup | Replaced with PostgreSQL custom-format encrypted off-site backup; no local fallback |
| PROD-003 | High | Corrected | No liveness/readiness endpoints | Separate process and DB/cache dependency endpoints with failure tests |
| PROD-004 | High | Corrected | Static files used basic storage and production `collectstatic` failed through Cloudinary's legacy override | WhiteNoise hashed/compressed storage; removed unused override app; production static build passes |
| PROD-005 | High | Corrected | Production origin/proxy/media settings could be incomplete | HTTPS origin/site, proxy and Cloudinary fail-fast gates |
| PROD-006 | Medium | Corrected | Logs lacked stable structure/correlation | JSON production formatter and safe request IDs |
| PROD-007 | High | External gate | No managed staging/production services currently provisioned | Cost baseline approved 2026-07-26; final deployment authorization and Blueprint sync required |
| PROD-008 | Critical gate | External gate | No proven PITR or logical restore | Paid managed database plus controlled restore exercise required before launch |
| PROD-009 | High | External gate | No configured uptime/worker/database/Redis alerts | Configure and test on staging/production host |
| PROD-010 | High | External gate | No staging load test or external penetration assessment | Execute after stable staging deployment |
| PROD-011 | Medium | Resolved | Frankfurt and the cost-conscious initial sizes were approved on 2026-07-26 | Measure Nairobi-to-staging latency and retain the documented cross-border-data caveat |
| PROD-012 | Medium | Open | Render Blueprint has not been validated by Render CLI/API | Validate immediately before sync; no deployment was attempted here |
| PROD-013 | High | Corrected | Staging could boot only by claiming privacy approval and enabling a non-console notification provider | Separate staging/production gates and isolated staging Blueprint; production gates remain strict |
| PROD-014 | High | External gate | Workspace has no usable Git remote and no authenticated Render CLI/API session | Connect the client-owned repository and Render account before Blueprint sync |
