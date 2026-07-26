# Phase 12 defect register

| ID | Severity | State | Evidence/impact | Resolution |
|---|---|---|---|---|
| SEC-001 | Critical | Corrected | Django 6.0.6 was below the July 2026 security release | Pin/install 6.0.7; verify dependency consistency |
| SEC-002 | High | Corrected | Toast content used `safe`, allowing message HTML to execute | Restore escaping and external dismiss behavior |
| SEC-003 | High | Corrected | Inbound SMS accepted unauthenticated public mutations | Disabled by default; secret authentication, size bound and negative tests |
| SEC-004 | High | Corrected | Audit records described as immutable but supported update/delete | Block instance/queryset/admin mutation and protect referenced actors |
| SEC-005 | High | Corrected | Product image fields accepted files without decoded type/dimension validation | Added size, extension, decoded format and pixel limits with tests |
| SEC-006 | High | Corrected | Production could collect data without approved controller/contact/privacy notice config | Added fail-fast production configuration gates |
| SEC-007 | Medium | Corrected | No enforced CSP; legacy inline scripts prevented safe activation | Added CSP and externalized application scripts/handlers |
| SEC-008 | Medium | Corrected | Regex request middleware was security theatre and false-positive prone | Replaced with real response hardening; ORM remains injection control |
| PRIV-001 | High | Corrected in application | No data-subject request/export workflow | Password-confirmed request/export; super-admin re-authenticated resolution; audit trail |
| PRIV-002 | High | Blocked by decision | No approved retention/lawful-basis/processor register | Client and qualified legal/compliance input required before automation/launch |
| SEC-009 | High | External gate | No staging penetration test, WAF/edge or production callback certification evidence | Phase 13 staging and approved external testing |
| SEC-010 | Medium | Open | Chart.js served from pinned CDN without locally verified asset hash | Self-host reviewed asset or remove charts before launch |
| SEC-011 | Medium | External gate | Complete dependency advisory scan unavailable in restricted environment | Run networked advisory scan in approved CI and retain report |
