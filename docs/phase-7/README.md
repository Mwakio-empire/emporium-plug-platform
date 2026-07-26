# Phase 7 - Inventory and transfers

Status: **core workflows implemented and locally verified** on 2026-07-22.

## Client operating model

- The business has three separately stock-owning shops in Nairobi County.
- The OTC shop is also the external supplier receiving hub.
- Two shops are in Gaberone Plaza: S18 and B03. They receive replenishment through internal transfers.
- Customer parcel delivery is Kenya-wide only. International delivery is outside the client MVP. Carriers, coverage and pricing belong to Phase 8.
- Customer pickup is normally from the second floor at S18, unless authorized staff direct otherwise.

Branch names are not hard-coded. `Branch.receives_supplier_stock` identifies the supplier receiving hub, allowing the client to change a shop name or add a future hub without a code rewrite.

## Delivered

- Supplier delivery intake restricted to a configured receiving hub.
- Idempotent delivery references and immutable line-level restock audits.
- Transfer lifecycle: requested, approved, dispatched, partially received, received, rejected or cancelled.
- A Gaberone Plaza shop manager can request inventory from OTC.
- OTC inventory management approves and dispatches the request.
- Dispatched units leave OTC sellable stock and remain in transit until received.
- Full and partial receipt history, including actor, time, quantity and note.
- Simple-product and variant-level inventory support.
- Reasoned and idempotent corrections, theft removal and damage quarantine.
- Cycle/spot counts with a single open count per branch.
- Counts are rejected if stock moved after the snapshot, avoiding stale corrections.
- Branch-specific low-stock transition alerts with durable spam suppression.
- Branch-scoped APIs and read-only audit administration.
- A branch-scoped staff workspace for intake, transfers, adjustments and cycle counts.
- Responsive storefront placement of the client's original logo artwork, with compact text branding in the navigation.

## Verification

- Workspace journey tests: 4 passed.
- Full suite: 315 passed, 1 skipped.
- Browser journey: supplier intake, transfer request, approval, dispatch, destination receipt and stock count all passed using an isolated disposable database.
- Django checks: passed.
- Migration drift: none.
- Compilation: passed.
- Migrations `branches.0002`, `inventory.0007` and `inventory.0008` applied successfully.

## Configuration still required

The current local database contains only a `Smoke Test Branch`; no production branch identities were invented. Before UAT, create the three official branch records, assign staff, and enable `receives_supplier_stock` only on OTC.

The client supplied `Gaberone Plaza S18` and `Gaberone Plaza B03`. The exact official OTC branch name/address and the complete street/postal details for both plaza shops must still be confirmed before production data is created.

## Deferred with justification

- Bulk import/export: the phase requirement is conditional on client need. File format, required columns and approval workflow need a business decision.
- Hardware barcode scanning: requires the actual scanner and browser/device acceptance test.
- Kenya-wide parcel delivery: the country boundary is confirmed, but Phase 8 still needs carriers, supported coverage, rate calculation, parcel tracking and liability rules.
- PostgreSQL concurrency evidence: SQLite cannot prove row locks; the existing concurrency test remains a staging gate.
