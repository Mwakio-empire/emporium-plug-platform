# Phase 2 Requirements Traceability

| Requirement | Implementation evidence | Test evidence | State |
|---|---|---|---|
| Customer registration by phone, optional email | Customer forms/serializer; inactive until signup OTP | `CustomerRegistrationTests` | Complete and verified |
| Customer login | Phone/email/username backend; customer JWT serializer | `LoginTests` | Complete and verified |
| Manager/admin-created staff | `StaffAccountProvisioningService`; scoped API and browser flows; secure admin | `StaffProvisioningTests` API and browser cases | Complete and verified |
| OTP verification and resend | Purpose-separated hashed OTP service, expiry, cooldown, attempt limit | `OTPAttemptLimitTests` | Complete and verified |
| Mandatory staff 2FA | HTML password then OTP; staff JWT login denied | Auth security tests | Complete and verified |
| Password reset | Enumeration-reduced OTP reset; token version increment | Password reset tests | Complete and verified |
| Logout/session invalidation | Django logout; JWT blacklist plus version revocation | HTML/API logout tests | Complete and verified |
| Throttling/account lockout | Cache throttles and persistent 5-failure/15-minute lockout | Login and OTP tests | Complete and verified |
| Sensitive POS manager approval | Fresh manager password, throttle, lockout, branch scope, audit | POS discount/void suites | Complete and verified; client accepted MVP control |
| No credential/PII logging | Identifying notification/payment log values removed | Source scan and auth tests | Complete at application layer |
| Service/API authorization | Shared permissions plus domain services | Cross-branch suites | Complete and verified |
| Impersonation safety | Disabled; no route or middleware | Source/URL inspection | Deferred with justification |
| Rider model decision | Branch `STAFF` plus validated `RiderProfile` | Logistics permission suite | Complete and verified |
| Identity uniqueness | Phone normalization, email constraint, collision audit command | Registration/provisioning tests and passing local collision audit | Complete and verified |

Phase 2 received final sign-off on 2026-07-21 after `audit_identity_collisions` passed and all verification gates remained green.
