# Phase 11 defect register

## Corrected

| Severity | Defect | Resolution |
|---|---|---|
| High | SMS delivery had no durable attempt or final-state ledger | Added notification and immutable attempt records |
| High | Provider retries were nested inside Celery retries | Provider now makes one call; Celery owns bounded backoff |
| High | Exhausted failures could disappear without staff action | Added branch-scoped manual follow-up queue and audited resolution |
| High | Development configuration could contact an external sandbox | Safe console provider is the default and is rejected in production |
| High | Repeated tasks could send the same event more than once | Added persisted pre-queue deduplication and terminal retry handling |
| Medium | WhatsApp fallback was implicit rather than policy-controlled | Disabled by default and restricted to catalogued critical events |
| Medium | Low-stock re-entry could be confused with a duplicate event | Each resolved-to-low transition receives its own occurrence identity |
| Medium | Provider metadata could become a route for message/OTP retention | Store fingerprints and sanitized response fields, never rendered bodies |

## Remaining production gates

| Severity | Gate | Required action |
|---|---|---|
| High | Real SMS/WhatsApp delivery is not certified | Run provider sandbox tests, then controlled production checks with written approval |
| High | Inbound provider webhook authenticity is not contract-verified | Confirm and implement the provider-supported authentication control before live use |
| Medium | Notification retention period is undecided | Resolve during Phase 12 with client and qualified privacy/legal input |
| Medium | WhatsApp operational/legal approval is absent | Keep disabled until the client approves channel, templates and processor terms |
