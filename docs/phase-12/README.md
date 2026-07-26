# Phase 12: security and privacy

Status: implemented and automated verification complete. Production approval, legal review, processor contracts, external penetration testing and client acceptance remain release gates.

## Delivered controls

- Django is pinned to the security-fixed 6.0.7 release.
- Enforced Content Security Policy, clickjacking, MIME, permissions and authenticated-response cache controls.
- Output escaping replaces unsafe rendering in customer/staff messages; remaining JavaScript behavior is externalized for CSP compatibility.
- Product image uploads are limited by size, extension, decoded format and dimensions.
- Inbound SMS is disabled by default and requires a constant-time checked application secret when enabled.
- Production refuses weak secrets, wildcard hosts, an unapproved privacy notice, missing controller identity/contact or the development notification provider.
- Audit records cannot be edited or deleted through model/queryset/admin paths, and referenced actors are protected from deletion.
- Customers can submit data-subject requests and download a password-confirmed, account-scoped JSON export.
- Privacy request resolution is restricted to an active super-admin, requires password re-authentication and records the outcome.
- Sentry defaults to no PII and all real outbound notification providers remain explicit opt-ins.

## Honest boundaries

- This work is a code/configuration review, not a penetration-test report or legal-compliance certification.
- M-Pesa callback origin authenticity depends on the provider/network deployment controls; application logic validates known transaction identifiers, amount, reference and idempotency.
- The management chart dependency is pinned to a CDN version but is not yet self-hosted with a verified asset hash.
- Retention values cannot be responsibly implemented until the client approves the schedule and qualified Kenyan legal/compliance advice confirms statutory and business requirements.
- Deletion requests require case-by-case review because financial, fraud-prevention and immutable audit records may need retention or anonymisation instead of deletion.
- Real provider certification, infrastructure/WAF configuration, backup access controls and external vulnerability scanning are Phase 13/production gates.

See [security review](security-review.md), [personal-data inventory](personal-data-inventory.md), [threat model](threat-model.md), [incident and breach runbook](incident-breach-runbook.md), [traceability](traceability.md), [defect register](defect-register.md), [browser acceptance](browser-acceptance.md), and [verification](verification.md).
