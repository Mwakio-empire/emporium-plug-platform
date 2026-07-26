# Phase 11: durable notifications

Status: implementation complete; automated and browser verification evidence is recorded in `verification.md`.

## Delivered scope

- A durable notification record is created before a background delivery job is queued.
- Each provider attempt retains its channel, provider, outcome, safe provider identifiers and sanitized response metadata.
- Stable event deduplication prevents a Celery retry or repeated business event from sending the same notification twice.
- Celery owns bounded retry and backoff. The provider service performs exactly one network request per attempt.
- Permanent or exhausted failures enter a manager-visible manual follow-up queue.
- Manual follow-up resolution records the manager, timestamp and evidence note.
- Development and test use a safe console provider that never contacts a real recipient.
- OTP values and rendered message bodies are not stored in the notification ledger or provider-response summaries.
- Kenya phone numbers are normalized to `+254XXXXXXXXX` before delivery.
- SMS events from identity, orders, payments, POS, fulfilment, inventory and reconciliation use the durable queue.
- WhatsApp fallback is disabled by default and limited to explicitly catalogued critical events when configured.

## Important boundaries

- `SUPPRESSED` means the safe development provider accepted the event without contacting a recipient; it is not proof of real delivery.
- Provider acknowledgement is not handset-read confirmation.
- WhatsApp fallback requires client approval, a lawful operational basis and production credentials before it may be enabled.
- The inbound SMS webhook remains public by provider necessity. Provider request authentication/signature controls must be confirmed against the contracted Africa's Talking product before production activation.
- Notification retention and personal-data deletion rules are Phase 12 privacy decisions. Recipient values are restricted operational personal data and are masked in staff interfaces.
- Real SMS/WhatsApp certification is a controlled external integration gate and is not performed by ordinary automated tests.

See [event catalog](event-catalog.md), [traceability](traceability.md), [defect register](defect-register.md), [browser acceptance](browser-acceptance.md), and [verification](verification.md).
