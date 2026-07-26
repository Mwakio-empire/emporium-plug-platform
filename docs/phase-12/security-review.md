# Security review

## Reviewed areas

Authentication, role/branch authorization, object access, CSRF, XSS, ORM usage, session/cookie settings, OTP and rate limiting, callbacks, uploads, logs/PII, error handling, admin permissions, dependency versions, response headers, audit integrity, payment/inventory fraud paths and request-size controls were inspected against the implemented code and existing automated tests.

## Confirmed strengths

- Financial and stock services already use atomic mutations, row locking, state validation and idempotency tests.
- Guest order access uses signed tokens rather than order number alone; authenticated users are limited to their own orders.
- Payment callback parsing is durable/idempotent and validates expected amount and known transaction identifiers before ordinary success.
- Staff actions are role/branch scoped and sensitive POS actions require manager password re-authentication.
- Production cookie, HTTPS, host and secret requirements are explicit configuration gates.
- Notification development mode cannot contact customers and Sentry PII is disabled by default.

## Findings corrected in Phase 12

- Patched Django 6.0.6 to 6.0.7.
- Removed a regex-based pseudo-firewall that blocked legitimate query text but did not provide SQL-injection protection.
- Removed unsafe toast rendering and inline handlers/scripts that conflicted with CSP.
- Added enforced CSP and additional browser security/cache headers.
- Added decoded image validation and upload/request limits.
- Disabled and authenticated inbound SMS instead of accepting spoofable public updates.
- Made audit records immutable through supported application/admin paths.
- Added customer privacy request/export and restricted operations handling.
- Added production privacy-notice/controller configuration gates.
- Upgraded Pillow from 12.2.0 to 12.3.0 after an authenticated advisory audit identified vulnerabilities fixed by 12.3.0.
- Re-ran Python and production JavaScript dependency audits and retained the results in the Phase 15 verification record.

## Residual findings

| Severity | Finding | Required resolution |
|---|---|---|
| High before launch | No approved controller identity, privacy notice, lawful-basis/retention register or processor record | Client plus qualified Kenyan legal/compliance review; production settings enforce notice/controller approval |
| High before launch | No external penetration test or production edge/WAF evidence | Conduct against staging after Phase 13 configuration |
| High before live payments | Callback/network controls and Daraja production certification are not externally verified | Safaricom certification plus controlled authorized production test |
| Medium | Management Chart.js is pinned but loaded from a CDN without a locally verified asset hash | Self-host a reviewed pinned asset before launch or remove charts |
| Medium | Database administrators can bypass application-level audit immutability | Restrict DB roles and evaluate append-only database controls in Phase 13 |
| Medium | No malware scanner for uploaded files | Keep uploads privileged; evaluate scanning if customer/public uploads are introduced |
| Medium | No approved automated retention/anonymisation jobs | Implement only after approved schedule and exceptions |
| Low | Django admin remains at the conventional path | Protect with super-admin auth, network/edge controls and monitoring; path obscurity is not a primary control |

## Conclusion

The repository's application security baseline is materially stronger and the corrected controls are testable. Phase 12 is not a statement of legal compliance, payment certification or production security approval. The high pre-launch external/client decisions above remain blocking release gates, not code defects that can be safely guessed.
