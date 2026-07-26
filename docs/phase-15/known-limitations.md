# Known limitations

These are accepted facts as of 2026-07-26, not hidden defects.

## Production and external proof

- Render staging/production resources have not been provisioned.
- Daraja and notification providers are verified through mocks/local controls, not complete provider certification.
- Scheduled-report email is locally failure-safe and configured for Brevo SMTP, but remains disabled until the business domain/sender and staging provider delivery are manually verified.
- Managed PostgreSQL PITR and the off-site logical archive have not been restored in a controlled host test.
- Representative PostgreSQL load/concurrency, Nairobi-to-Frankfurt latency, external security and client UAT remain pending.
- Local SQLite skips one `select_for_update` test and cannot prove row-lock behavior.

## Business configuration

- The local database now identifies its single stocked demo branch as Gaberone Plaza S18 for pickup-flow testing, but it is not the complete official three-branch production dataset.
- Official OTC name/address, full shop addresses, real staff assignments and pickup slots require controlled configuration.
- Parcel handoff, arrival and collection records exist for future controlled use, but public automated parcel checkout is intentionally disabled. Launch checkout is S18 pickup only; town parcels are arranged through WhatsApp and must be recorded by staff after the route and final charge are agreed.
- Pickup working days are Monday-Saturday; Kenyan public holidays are not modelled.
- WhatsApp assists conversation only; it does not reserve stock or verify payment.

## Financial and returns boundaries

- Automated M-Pesa refunds are not implemented. Approved return refunds are tracked for manual reconciliation.
- Partial/over payments and unidentified callbacks enter reconciliation rather than ordinary success.
- Exact order-total equality and order-item multiplication are enforced by services/tests, not complete database expressions.
- Customer-entered Paybill/reference values never prove payment.

## Data/security design debt

- `StockAuditLog` and `OrderStatusHistory` are append-only by service convention/permissions, not database-trigger immutability.
- Category cycles, some promotion rules and product non-negative price rely on application validation rather than complete DB constraints.
- Authorization permission classes are duplicated across apps; behavior is tested but not yet centralized.
- API documentation is Markdown; no published, versioned OpenAPI compatibility contract exists.
- Legal compliance and security certification cannot be claimed from code review.

## Operational/UI boundaries

- Barcode scanners, receipt printers, fiscal/tax devices and offline POS are not certified.
- Bulk catalog/inventory import/export is not implemented because no format/workflow is approved.
- Route optimization, public live rider maps and native mobile apps are absent.
- Image search is deferred; text/category/filters and WhatsApp assistance remain discovery paths.
