# Threat model

## Protected assets

- Customer identity/contact, addresses, order and notification history.
- Staff credentials, OTP state, sessions, roles, branches and approval authority.
- Inventory availability, transfers and stock movement history.
- Order totals, M-Pesa/payment identifiers, cash shifts, refunds and reports.
- Audit history, provider credentials, backups and deployment secrets.

## Trust boundaries

1. Public browser to Django over HTTPS.
2. Staff/rider browser to role- and branch-scoped application services.
3. Django to PostgreSQL, Redis, Celery workers and object storage.
4. Django to Daraja, Africa's Talking, optional WhatsApp and Sentry.
5. Provider callbacks into public payment/SMS endpoints.
6. Operations staff to hosting, database, backups and secrets.

## Priority abuse cases and controls

| Threat | Primary controls | Residual risk |
|---|---|---|
| Account takeover | Password validation, OTP, staff 2FA, throttling/lockout, session invalidation, re-authentication | SIM swap and compromised email/phone require operational support checks |
| Cross-branch access | Central permission classes, service checks, branch-scoped querysets and tests | New endpoints can regress without permission tests |
| Stored/reflected XSS | Django escaping, CSP, no inline event handlers, validated image types | Third-party chart script remains a supply-chain dependency |
| CSRF/session theft | Django CSRF middleware, secure/HTTP-only/SameSite cookies in production, HTTPS | Host compromise or malicious browser extension is out of application scope |
| SQL injection | Django ORM and validated parameters | Raw SQL introduced later requires dedicated review |
| Payment forgery/replay | Known request IDs, amount/reference checks, unique receipts, callback inbox/idempotency | Daraja callback source authentication is deployment/provider dependent |
| Inventory double mutation | Atomic transactions, row locks, mutation ledger and idempotent reversal | Database/operational recovery still needs Phase 13 testing |
| Spoofed inbound SMS | Disabled by default; secret checked with constant-time comparison | Secret transport/configuration must match the contracted provider capability |
| Malicious upload | Size, extension, decoded image format and dimension validation | Malware scanning is not implemented; only staff/admin uploads should be permitted |
| Audit tampering | Immutable model/queryset/admin paths and protected actor references | Database administrators can alter records; database-level append-only controls are deferred |
| PII leakage | Safe logs, masked notification UI, no Sentry PII by default, authenticated no-store responses | Operational exports/backups need Phase 13 access and retention controls |
| Denial of service | Upload/request limits, throttling, bounded retries | Edge rate limiting, WAF and capacity/load evidence remain production work |

## Review trigger

Repeat this threat model when adding a provider, changing authentication, enabling public uploads, introducing offline POS, changing payment callbacks, or materially changing hosting/topology.
