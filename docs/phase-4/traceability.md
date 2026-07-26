# Phase 4 Requirements Traceability

| Requirement | Evidence | State |
|---|---|---|
| Review cart | Checkout page renders locked item description, quantity and current cart subtotal | Complete and verified |
| Delivery or pickup | UI and service enforce mutually exclusive fulfilment fields | Complete and verified |
| Branch selection | Active branch and cart-branch match enforced | Complete and verified |
| Zone or pickup slot | Branch ownership, active state and pickup expiry enforced | Complete and verified |
| Customer details | Guest/customer phone, optional name and email validated and stored | Complete and verified |
| Delivery fee and final total | Preview and final API return subtotal, discount, fee and payable total | Complete and verified |
| Coupon | Preview is non-consuming; final redemption is transactional and row-locked | Complete and verified |
| M-Pesa STK | Initiation and bounded browser polling exist | Implemented; provider certification belongs to Phase 5 |
| Approved cash scenario | Client approved cash for delivery and pickup; exact payable totals and confirmation are tested | Complete and verified |
| Explicit confirmation | Required checkbox follows successful total review; API rejects absent/false confirmation | Complete and verified |
| Idempotent order creation | Unique UUID, request fingerprint, owner binding and safe replay | Complete and verified |
| Payment progress states | Creating, initiating, pending, confirmed, fallback and error states | Complete for Phase 4; reconciliation is Phase 5 |
| Confirmation and tracking | Protected tracking page and API for customer/guest | Complete and verified |
| Post-commit notification | Cart flush and SMS enqueue use `on_commit` | Complete and verified |
| Guest checkout | Phone-only guest delivery/pickup supported | Complete and verified |
| Signed guest access | Seven-day signed bearer token sent outside URL query logs | Complete and verified |
| Optional account creation | Confirmation links to customer registration without requiring it | Complete and verified |

## Known verification boundary

The final-unit locking test requires PostgreSQL and is skipped by the local SQLite suite. Phase 1 already contains the database locking path; staging must run the PostgreSQL concurrency suite before release.
