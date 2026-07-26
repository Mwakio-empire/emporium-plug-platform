# Phase 9 browser acceptance

Executed against isolated SQLite databases with synthetic identities and `RETURN_REQUEST_WINDOW_DAYS=7`. No live customer or refund/payment provider was contacted.

| Journey | Result |
|---|---|
| Confirmed purchaser sees and submits product review | Pass |
| Review becomes awaiting moderation and cannot be resubmitted | Pass |
| Customer submits item/quantity return request and sees pending history | Pass |
| Branch manager completes mandatory 2FA and sees only operational queues | Pass |
| Manager approves review with mandatory moderation reason | Pass |
| Manager assesses return, selects sellable disposition and pending-manual refund | Pass |
| Sellable stock increases once and audit events are written | Pass |
| Approved queues clear after successful decisions | Pass |
| Approved WhatsApp ordering number remains visible | Pass |
| Eligible non-clothing product appears in the seven-day self-service return page | Pass |
| Support-only clothing product is excluded from self-service return controls | Pass |
| Product pages show the correct seven-day or support-only wording | Pass |

Database verification after the workflow journey showed stock `5 -> 6`, return `APPROVED`, refund `PENDING_MANUAL`, review approved, and six audit events. A final policy-specific journey displayed only the eligible kettle in the return form while excluding a support-only shirt. The temporary databases and servers were removed afterward.
