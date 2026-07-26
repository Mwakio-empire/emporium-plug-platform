# API reference

This is the implemented MVP surface, not a public compatibility guarantee. JSON endpoints use Django REST Framework. Session-authenticated browser requests require CSRF; JWT endpoints use the issued access token. Branch/object authorization is enforced server-side.

## Public catalog and fulfilment configuration

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog/categories/` | Visible nested categories. |
| GET | `/api/catalog/products/` | Active catalog with supported filters/sorting/pagination. |
| GET | `/api/catalog/products/{slug}/` | Active product detail. |
| GET | `/api/logistics/zones/` | Legacy delivery-zone configuration. Public launch checkout does not expose self-service delivery. |
| GET | `/api/logistics/pickup-slots/` | Active, non-expired pickup slots. |

## Identity

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/users/api/register/` | Public/throttled | Start customer phone registration. |
| POST | `/api/users/api/register/verify/` | Public/throttled | Verify signup OTP. |
| POST | `/api/users/api/login/` | Public/throttled | Customer JWT login. |
| POST | `/api/users/api/token/refresh/` | Refresh token | Rotate/version-check access. |
| POST | `/api/users/api/logout/` | Authenticated | Blacklist/logout token session. |
| GET/PATCH | `/api/users/api/profile/` | Authenticated owner | Read/update own profile. |
| POST | `/api/users/api/staff/` | Branch manager/super admin | Provision branch-scoped staff invite. |
| POST | `/api/users/api/staff/invite/activate/` | Public with valid invite | Activate invited staff account. |
| POST | `/api/users/api/staff/{id}/invite/resend/` | Authorized manager | Reissue valid staff activation. |

## Checkout and orders

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/checkout/preview/` | Guest/customer session | Revalidate stock/prices, S18 pickup and coupon without creating an order. |
| POST | `/api/checkout/init/` | Guest/customer session | Idempotently create a confirmed S18-pickup order. |
| POST | `/api/checkout/pay/` | Owner or signed guest token | Initiate STK for the pending order. |
| POST | `/api/checkout/pay/fallback/` | Owner or signed guest token | Submit a typed reference for staff review; not proof of payment. |
| GET | `/api/orders/{order_number}/status/` | Owner or signed/expiring guest access | Read that order's status only. |

Public launch checkout accepts `ONLINE_PICKUP` only and requires an active S18 pickup arrangement, phone, approved payment method and explicit confirmation. A forged `ONLINE_DELIVERY` request is rejected and directed to the approved WhatsApp-assisted town-parcel process. The server recomputes totals and never trusts browser amounts.

## Inventory

All paths below require an inventory controller and are branch-scoped.

- `GET/POST /inventory/intakes/`
- `POST /inventory/adjustments/`
- `GET/POST /inventory/counts/`
- `POST /inventory/counts/{count_id}/lines/{line_id}/`
- `POST /inventory/counts/{count_id}/complete/`
- `POST /inventory/counts/{count_id}/cancel/`
- `GET/POST /inventory/transfers/`
- `POST /inventory/transfers/{id}/approve|dispatch|receive|confirm|reject|cancel/`

Mutations require reason/reference data as applicable and use locked inventory services plus audit entries.

## Logistics

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/logistics/my-deliveries/` | Rider profile | Own assigned queue. |
| POST | `/api/logistics/delivery/{assignment_id}/update/` | Assigned rider | Validated physical delivery transition. |
| POST | `/api/logistics/assign-rider/` | Branch manager/super admin | Assign an available same-branch rider. |
| POST | `/api/logistics/confirm-pickup/` | Branch staff or above | Attempt-limited pickup-code confirmation. |

## Marketing and returns

- `GET/POST /marketing/reviews/`: public approved-review read; authenticated verified-purchase creation.
- `GET /marketing/reviews/moderation/` and `POST /marketing/reviews/{id}/moderate/`: manager queue/decision.
- `GET/POST /marketing/returns/`: customer's own requests.
- `GET /marketing/returns/branch/` and `POST /marketing/returns/{id}/decide/`: branch manager operations.

## Reports

| Method | Path | Access |
|---|---|---|
| GET | `/api/reports/my-shift/` | Staff or above; own/authorized shift scope. |
| GET | `/api/reports/branch-daily/` | Branch manager or above. |
| GET | `/api/reports/operations/` | Branch manager or above; JSON/CSV/PDF by supported parameters. |

Date ranges are validated, timezone is Nairobi, and branch scope is derived from authorization rather than trusted query parameters.

## Payment and notification callbacks

| Method | Path | Authentication/control | Purpose |
|---|---|---|---|
| POST | `/payments/mpesa/callback/` | Daraja callback parsing plus retained event/reconciliation controls | Idempotent callback ingestion; exact amount/identifier/receipt checks before settlement. |
| POST | `/payments/mpesa/{payment_id}/manual-confirm/` | Authorized branch staff plus manager full-password re-authentication | Controlled reconciliation. |
| POST | `/payments/mpesa/webhook-events/{event_id}/resolve/` | Authorized operations user | Resolve retained unknown/malformed event with reason. |
| POST | `/notifications/sms/inbound/` | Disabled by default; configured shared token when enabled | Inbound customer delivery confirmation/dispute. |

Do not log request bodies for OTP, payment or callback endpoints. Preserve provider IDs and sanitized outcome metadata for audit/reconciliation.
