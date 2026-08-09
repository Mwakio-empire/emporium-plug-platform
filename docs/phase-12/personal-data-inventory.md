# Personal-data inventory and decisions required

This inventory describes implemented fields and flows. It does not decide the legal basis or retention period on the client's behalf.

| Data | Purpose in the implementation | Main recipients/processors | Current lifecycle |
|---|---|---|---|
| Name, phone, optional email | Account, checkout, pickup/delivery contact, support | Hosting/database; Africa's Talking when SMS is enabled | Account and linked order records; no approved deletion schedule yet |
| Password hash, OTP digest/state, session data | Authentication and recovery | Hosting/database/Redis | OTP/session expiry implemented; passwords are never exported |
| Delivery address/zone and pickup details | Fulfilment | Staff, rider, hosting/database | Stored with order; retention decision pending |
| Town-parcel quote recipient, phone/email, county, town, preferred area, basket snapshot and published transport terms | Provide a staff-verified pre-order transport quote and protected customer follow-up | Authorized branch manager/super admin, hosting/database; SMS/email providers for quote-ready notice | Quote access expires cryptographically for guests; quote/history retention and eventual anonymisation require client/legal approval |
| Order items, prices, status and returns | Contract fulfilment, support, reporting | Hosting/database, relevant staff | Financial/operational record; retention decision pending |
| M-Pesa phone, request/receipt/reference and amount | Payment, reconciliation and fraud handling | Safaricom/Daraja, hosting/database | Durable financial record; credentials and PIN are never stored |
| Notification recipient digest, event and provider result | Delivery evidence, retry and support | Africa's Talking/approved WhatsApp provider | Message bodies and OTPs are not stored in the notification ledger |
| Restock-alert mobile number, item and opaque cancellation token | Fulfil a customer-requested one-time availability alert | Hosting/database; Africa's Talking when SMS is enabled | Active request expires after 90 days; terminal-record retention still requires client/legal approval |
| Reviews | Customer feedback and moderation | Public storefront after approval | Account-linked; moderation state retained |
| Staff/rider identity, branch and activity | Authorization, accountability, fulfilment | Client management and hosting/database | Audit-linked actors are protected from deletion |
| IP address and security/audit events | Security, fraud investigation and accountability | Authorized management; Sentry only if configured | Immutable audit history; exact retention decision pending |
| Uploaded product images | Catalog display | Cloudinary or S3-compatible provider when enabled | Not normally personal data; staff must not upload people/IDs without approval |

## Production decisions requiring client/legal approval

1. Confirm the data controller's legal name, postal/contact details and privacy contact/DPO route.
2. Approve a purpose-by-purpose lawful-basis register and the customer privacy notice.
3. Confirm whether ODPC registration is required/completed and record the registration details.
4. Approve retention periods for accounts, guest checkout, financial/payment records, audit/security logs, notifications, carts, reviews, returns and backups.
5. Approve correction, erasure/anonymisation, objection and portability handling procedures, including identity verification.
6. Record processors, contracts, hosting regions and cross-border safeguards for hosting, storage, Safaricom, Africa's Talking, WhatsApp and Sentry.
7. Decide minimum-age/children's-data policy and marketing-consent rules before those features are added.
8. Name incident owners and approve the breach escalation/contact tree.
