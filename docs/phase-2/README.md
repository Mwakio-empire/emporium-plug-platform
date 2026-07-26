# Phase 2 — Identity, Authentication and Authorization

## Status

Phase 2 is complete as of 2026-07-21. The full suite passes (240 tests, 1 intentional skip), Django system checks pass, migration drift is clean, all Python source parses, installed dependencies are consistent, and the identity-collision audit passes. The client accepted the manager credential decision in `adr-001-manager-approval-credential.md`. This phase does not claim production readiness for later payment, fulfilment or deployment phases.

## Implemented controls

### Customer identity

- Customer self-registration always forces the `CUSTOMER` role.
- API and HTML registrations create inactive accounts.
- A signup OTP must be verified before the account is activated or API tokens are issued.
- Passwords are checked by Django's configured password validators.
- Customer API login issues 15-minute access tokens and rotating, blacklisted refresh tokens.
- Profile updates cannot change email or role.

### OTP and password reset

- OTPs use `secrets`, are stored only as password hashes and expire after 10 minutes.
- Only the newest unverified OTP for a purpose is usable.
- Resends have a 60-second cooldown.
- Five incorrect attempts make an OTP unusable.
- Signup, staff invitation, staff login and password reset use separate OTP purposes.
- Password reset increments the user's token version, invalidating all older access and refresh tokens.
- Pending OTP/reset browser state expires after 10 minutes and the session key is rotated when that state is created.

### Staff authentication and provisioning

- `STAFF`, `INVENTORY_MANAGER`, `BRANCH_MANAGER` and `SUPER_ADMIN` accounts must complete password authentication plus staff OTP before an HTML session is created.
- Staff login through the customer JWT endpoint is denied, preventing a 2FA bypass.
- Staff accounts cannot be created through public registration.
- Branch managers can invite only `STAFF` accounts for their own branch through the protected staff API.
- Super admins can invite `STAFF`, `INVENTORY_MANAGER` and `BRANCH_MANAGER` accounts for an explicit active branch.
- Managers have a protected browser invitation screen, and invitees have a public activation screen linked from sign-in.
- Invitations create inactive accounts with unusable passwords. Staff verify a separate invitation OTP and set a validated password before their normal password-plus-OTP login.
- Django-admin provisioning remains restricted to Django superusers.
- Branch-dependent roles are required by model and database constraints to belong to a branch.

### Brute-force and session protection

- Login failures are stored on the account, not only in process memory.
- Five password failures lock an account for 15 minutes.
- IP/identifier login limits, API throttles, signup limits, OTP limits and manager re-authentication limits provide additional protection.
- Browser redirect targets are restricted to local, allowed-host URLs.
- Browser sessions use HttpOnly and SameSite cookies; production enables Secure cookies.
- CSRF protection remains mandatory for session-authenticated mutations.
- HTML logout destroys the session. API logout blacklists the submitted refresh token and increments token version, globally revoking that user's existing JWTs.

### Authorization model

Authorization classes now live in `apps/users/permissions.py` so inventory, logistics, marketing and reporting endpoints share the same definitions.

| Capability | Customer | Branch staff | Rider profile | Inventory manager | Branch manager | Super admin |
|---|---:|---:|---:|---:|---:|---:|
| Customer storefront/account | Yes | No | No | No | No | No |
| POS operation | No | Yes | No | No | Yes | Yes, with branch context |
| Rider delivery queue/update | No | No | Own assignments only | No | No | No |
| Pickup confirmation | No | Yes | No | Yes | Yes | Yes |
| Inventory transfer management | No | No | No | No | Own branch scope | Global |
| Branch reports/return decisions | No | No | No | No | Own branch scope | Global where supported |

Rider access is deliberately capability-based: a rider is a branch `STAFF` user with a one-to-one `RiderProfile`. A rider profile must match the user's branch. Rider accounts are excluded from generic staff/POS capabilities and can update only assignments belonging to their own profile.

### Sensitive manager actions

Discount overrides and voids require live manager password re-authentication. Attempts are rate-limited, persistent failures contribute to account lockout, branch managers may authorize only their branch, and the decision is audited. Passwords and attempted identifiers are not written to audit descriptions. The client accepted full-password re-authentication as the MVP control on 2026-07-21; a separate manager PIN is deferred.

### Impersonation decision

Impersonation is disabled. There is no route or middleware that can switch identity, and `IMPERSONATION_ENABLED` is false. Historical audit action names remain for schema compatibility. It must not be enabled until the product includes fresh super-admin re-authentication, a persistent on-screen banner, expiry, target restrictions, and start/stop audit events.

## API behavior changes

- `POST /api/users/api/register/` returns the inactive user and `verification_required: true`; it does not return tokens.
- `POST /api/users/api/register/verify/` accepts `identifier` and `code`, activates the customer and returns tokens.
- `POST /api/users/api/login/` is customer-only.
- `POST /api/users/api/logout/` requires the refresh token and revokes the user's existing JWTs.
- `POST /api/users/api/token/refresh/` rejects blacklisted or version-revoked refresh tokens.
- `POST /api/users/api/staff/` creates a scoped inactive staff invitation.
- `POST /api/users/api/staff/invite/activate/` verifies the invitation and sets the staff password.
- `POST /api/users/api/staff/{user_id}/invite/resend/` reissues an invitation within the actor's scope.

These are intentional security-breaking API changes. Any mobile or frontend client built against the former immediate-token registration response must be updated before deployment.

## Deployment checklist

1. Back up the target database and rehearse restoration.
2. Deploy code and run `python manage.py migrate`; this includes user security fields and Simple JWT blacklist tables.
   The migration also purges pre-Phase-2 OTP rows because they may contain legacy plaintext codes; affected users must request a new code.
3. Use Redis or another shared production cache. Local-memory throttles do not coordinate across multiple application workers.
4. Configure HTTPS, allowed hosts, CSRF trusted origins, secure cookies and trusted proxy headers for the actual domain.
5. Configure and verify the SMS provider using test accounts. Never use real OTPs in logs or support tickets.
6. Run `python manage.py audit_identity_collisions`; deployment must stop if it reports a collision.
7. Create staff only from an approved manager/super-admin session and verify role/branch assignment.
8. Confirm staff invitation, activation, 2FA, customer signup, reset, lockout and logout against staging.
9. Run the full automated suite and a security review before production activation.

## Known limitations and deferred work

- Manager-scoped staff invitation and public invitation-activation screens are available under `/accounts/staff/`; navigation from the operational manager dashboard is deferred until that dashboard is standardized.
- Staff API access is intentionally unavailable because there is not yet a 2FA-capable staff token exchange.
- SMS is the only second factor; TOTP/passkeys, recovery codes and trusted-device management are not implemented.
- There is no user-facing active-device/session list or selective remote logout.
- Account lockout can be abused to temporarily deny access to a known account. Operational unlock procedures and alerting should be added before a large rollout.
- SMS delivery depends on Celery, the broker and provider credentials. Successful automated tests do not prove provider delivery.
- Provider-side logs and infrastructure telemetry must also be configured not to retain OTP message bodies; application code alone cannot guarantee third-party retention policy.
- The former normalized-phone collision was resolved using the client-confirmed owner and replacement number. The replacement identifier is not recorded in project documentation or application logs.
- Authorization is centralized for Phase 2 endpoints and staff provisioning is enforced again in its service layer. A later pass should continue moving branch assertions from views into services across every domain.
- External penetration testing, load testing, privacy review and production secret rotation are still required.

Compared with mature ecommerce platforms, Phase 2 now has the essential identity boundaries—verified registration, scoped staff invitations, staff 2FA, token revocation, lockouts, role/branch scoping and audited elevation—but it does not yet have passkeys, device/session management, risk-based authentication, security alerts or a dedicated identity provider.

## Verification coverage

Automated tests cover:

- inactive registration and OTP activation;
- hashed OTP storage, expiry, one-time use, resend cooldown and five-attempt enforcement;
- customer JWT login and refresh;
- prevention of staff JWT/2FA bypass;
- manager/super-admin staff-provisioning scope and invitation activation;
- manager browser invitation, customer denial and browser invitation activation;
- prevention of inactive privileged-account reactivation through customer signup;
- persistent login lockout;
- staff password-plus-OTP session creation;
- open-redirect rejection;
- CSRF rejection;
- password-reset token revocation;
- API logout and refresh-token revocation;
- existing cross-branch inventory, logistics, return and reporting boundaries.
