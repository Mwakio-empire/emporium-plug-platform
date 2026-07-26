# Phase 9 traceability

| Requirement | Implementation/evidence | State |
|---|---|---|
| Fixed/percentage coupon | `Coupon`, `PromotionService`, checkout tests | Complete and verified |
| Dates/minimum/global limit | model constraints and locked service validation | Complete and verified |
| Per-customer limit | keyed authenticated/guest redemption identity | Complete and verified |
| Branch scope | optional coupon-to-branch relation | Complete and verified |
| Product/category scope | no confirmed client requirement | Deferred with justification |
| Stacking policy | one coupon; no manual discount stacking | Complete and documented |
| Atomic redemption | row locks plus one order redemption ledger | Complete and verified |
| Flash sales | validated time/price/overlap and checkout price locking | Complete and verified |
| Promotion audit | admin change and redemption audit entries | Complete and verified |
| Bundle deals | no client approval | Deferred with justification |
| Verified-purchase reviews | order/item ownership service | Complete and verified |
| One-review policy | conditional database uniqueness | Complete and verified |
| Moderation | manager queue, reason, actor, timestamp, audit | Complete and browser verified |
| Rating/privacy/abuse | approved-current aggregation, first-name display, rate limit | Complete and verified |
| Return eligibility window | approved seven-day setting plus explicit product policy | Complete and verified |
| Clothing exclusion | safe-default `SUPPORT_ONLY`; eligible non-clothing products explicitly opt in | Complete and verified |
| Quantity/branch controls | item row lock, cumulative check, manager branch isolation | Complete and verified |
| Condition/disposition | sellable, damaged and quarantine paths | Complete and browser verified |
| Refund status | explicit manual statuses, no automated-refund claim | Complete and verified |
| Duplicate approval | pending-only transition plus idempotent stock reference | Complete and verified |
