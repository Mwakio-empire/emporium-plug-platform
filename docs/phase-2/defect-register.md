# Phase 2 Closure Defect Register

## Open

None.

## Resolved in closure pass

- The client confirmed user ID 1 owns the previously shared normalized phone identity and supplied a verified replacement for customer user ID 2. The replacement was applied atomically, the expired never-activated signup holding it was removed under the existing 24-hour purge rule, and an identifier-free audit event was recorded. `audit_identity_collisions` now passes.

- Inactive privileged accounts could enter customer signup verification. Role and activation-state controls now prevent it.
- Unverified-account cleanup could target any old inactive account. It now deletes only never-activated customer registrations.
- Rider tests contradicted the profile-only capability policy. They now enforce rider-only delivery access and deny rider counter actions.
- Branch managers could not create branch staff. Scoped invitation, activation and resend APIs plus browser invitation/activation screens now exist with service authorization and audits.
- Direct OTP expiry, reuse and resend-cooldown coverage was missing and has been added.
- Logs exposed phone numbers, emails, fallback payment references or inbound message text; those statements now use internal IDs, counts and exception types.
- The client accepted full manager-password re-authentication for discounts and voids as the MVP control on 2026-07-21. A separate manager PIN is deferred.
