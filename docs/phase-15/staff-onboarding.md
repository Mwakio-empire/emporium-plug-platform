# Staff onboarding and role management

## Before creating an account

Confirm the employee's official name, verified Kenyan phone, role, employing branch, manager and start/end dates. Use one person per account. Shared cashier, manager or rider credentials are prohibited.

## Supported identities

- `STAFF`: branch POS and permitted fulfilment work.
- `INVENTORY_MANAGER`: branch inventory operations.
- `BRANCH_MANAGER`: own-branch management, reports and approvals.
- `SUPER_ADMIN`: global administration; branch mutations still require explicit context.
- Rider capability: a branch-bound `RiderProfile` attached to a staff user, not a separate user role.
- `CUSTOMER`: cannot be promoted through customer-facing registration.

## Invite procedure

1. Manager signs in with staff OTP and opens `/accounts/staff/invite/`.
2. Enter verified phone/email, role and branch. Do not create staff through customer signup.
3. Give the employee the activation route through an approved private channel; never send a password.
4. Employee activates, sets their own strong password and completes mandatory staff OTP.
5. Manager verifies the employee can access only their branch and required workspace.
6. Record training completion and issue no broader permissions “just in case.”

Resend an invite only from the authorized manager operation. Repeated activation/OTP failures require identity verification, not bypassing controls.

## Role changes and offboarding

Role/branch changes require manager or super-admin authorization, reason and verification that open shifts, assigned deliveries, transfers and unresolved approvals have an owner. On exit: deactivate the user, invalidate sessions/tokens, reassign operational work, remove rider availability and review recent privileged audit events. Do not delete staff accounts that own audit history.

## Manager approval credential

The MVP uses the manager's full password for discounts, voids and payment confirmation. Never ask a manager to reveal it to a cashier, type it where cameras/customers can observe, or record it in notes. A short PIN is deferred because it needs a separate hash, rotation, recovery and lockout design.
