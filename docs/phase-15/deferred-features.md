# Deferred feature list

| Feature | Priority | Reason / prerequisite |
|---|---:|---|
| Offline/PWA POS | P3 | Requires encrypted local storage, conflict resolution, duplicate-sale prevention and recovery design. |
| Barcode scanners/receipt printers | P3/conditional | Requires actual hardware/device/browser certification. |
| Fiscal/tax-device integration | Decision required | Kenyan tax adviser/client must define obligation/provider. |
| Bulk catalog/inventory import/export | P2/conditional | Client must approve columns, validation, preview, error and authorization workflow. |
| Automated refunds | P2 | Requires provider refund API, approvals, ledger and settlement reconciliation. |
| Product/category coupon scope and bundles | P2 | Not requested; stacking/allocation rules require approval. |
| Public-holiday pickup calendar | P2 | Client must decide policy and calendar ownership. |
| Image search | P3 | Adds vector service, moderation/privacy, cost and relevance evaluation. |
| Elasticsearch/OpenSearch | P3 | Current scale does not demonstrate need. |
| Advanced routing/live rider tracking | P3 | Needs carrier/GPS/privacy design and value proof. |
| Loyalty programme | P3 | Earn/redeem/expiry/accounting rules not approved. |
| Marketplace/vendors | Out of scope | Client is one unified retailer. |
| Native mobile applications | P3 | Responsive web must launch and stabilize first. |
| Advanced personalization | P3 | Requires lawful data, consent/purpose and measurable benefit. |

Deferred does not mean impossible. Each item begins with discovery/ADR, risk review, cost estimate and testable acceptance criteria.
