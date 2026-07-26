# Phase 14: testing strategy

Status: local automated and browser verification is complete. Staging, provider, restore, load and client-acceptance gates remain external and must pass before production approval.

## Delivered

- Layered Django coverage for models, services, permissions, APIs, templates, payments, inventory, fulfilment, notifications and reports.
- Checkout browser verification on desktop and a 390 x 844 mobile viewport.
- Live delivery-zone fee and payable-total recalculation.
- Explicit, customer-required delivery versus S18-pickup selection with neither option assumed, plus matching fulfilment-workspace labels.
- Inline valid and invalid coupon feedback, including the saving for an accepted coupon.
- Accessible cart icon with quantity badge and a favicon derived from the approved logo's trolley emblem.
- A consolidated manual UAT guide and results template.

## Phase exit position

The repository can pass the local Phase 14 gate, but the commercial release gate is not yet complete. The following cannot be truthfully proven on the local SQLite/development setup:

- PostgreSQL concurrency behavior under representative load;
- Daraja sandbox callback, polling and failure journeys;
- Africa's Talking or other approved provider sandbox delivery;
- managed PostgreSQL backup restoration and recovery timing;
- staging accessibility, security and load testing;
- client user-acceptance testing.

These are controlled external tests, not missing application claims. Record their results before migration or production approval.

See [verification](verification.md), [traceability](traceability.md), the [manual UAT guide](../testing/manual-uat-guide.md), and the [UAT results template](../testing/manual-uat-results-template.md).
