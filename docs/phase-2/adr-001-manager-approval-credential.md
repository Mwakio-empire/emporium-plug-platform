# ADR-001: Manager Approval Credential

Status: Accepted - 2026-07-21

## Context

The business document describes a manager PIN for discounts and voids. The current POS performs fresh authentication with the manager's full account password. It rate-limits failures, applies persistent lockout, enforces branch scope and writes an audit record.

## Decision

Retain full manager-password re-authentication for the MVP. The client accepted this control on 2026-07-21. Do not introduce an undocumented short PIN. A future PIN requires its own hashed storage, setup, rotation, recovery, attempt limits and compromise procedure.

## Consequences

- Security is stronger than a short numeric PIN and there is no second reusable secret to manage.
- Approval is slower and may not match the preferred counter workflow.
- If a PIN is required, implement it deliberately and never store or log the raw value.
