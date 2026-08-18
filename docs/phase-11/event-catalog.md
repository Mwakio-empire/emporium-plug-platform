# Notification event catalog

| Event | Template key | Class | Default channel | WhatsApp fallback |
|---|---|---|---|---|
| OTP | `security.otp` | Critical | SMS | No |
| Order placed | `order.placed` | Important | SMS | No |
| Delivery quote ready | `delivery.quote_ready` | Important | SMS and email when configured | Customer support link only |
| Payment confirmed | `payment.confirmed` | Critical | SMS | Allowed only when globally enabled |
| Walk-in receipt | `pos.receipt` | Important | SMS | No |
| Order cancelled | `order.cancelled` | Important | SMS | No |
| Delivery status | `delivery.status` | Important | SMS | No |
| Pickup ready | `pickup.ready` | Important | SMS | No |
| Pickup reminder | `pickup.reminder` | Important | SMS | No |
| Collection confirmed | `pickup.collected` | Informational | SMS | No |
| Delivery dispute | `delivery.dispute` | Critical | SMS | Allowed only when globally enabled |
| Low stock | `inventory.low_stock` | Important | SMS | No |
| Back in stock | `catalog.back_in_stock` | Informational | SMS | No |
| Transfer | `inventory.transfer` | Important | SMS | No |
| POS void | `pos.void` | Critical | SMS | Allowed only when globally enabled |
| Shift variance | `shift.variance` | Critical | SMS | Allowed only when globally enabled |

## Delivery rules

1. The business event supplies a stable reference and occurrence value.
2. The event is persisted before Celery is called.
3. The rendered body is represented only by a SHA-256 fingerprint in durable storage.
4. One provider call is made for each recorded attempt.
5. Successful, suppressed and permanent outcomes are terminal. Retryable failures use bounded Celery backoff.
6. A repeated event with the same deduplication identity is not queued again.
7. Exhausted or permanent failures become manual follow-up work.
8. WhatsApp is attempted only for an allow-listed critical event and only when the global setting and credentials are present.

Customer restock alerts are one-shot, product/variant-specific requests. They expire after 90 days, are rate limited, do not reserve inventory and are queued only after the subscription and durable notification event commit successfully.

Delivery-quote-ready messages are queued only after staff publication commits. They contain the quote reference and a protected status URL; guest access is carried in the URL fragment so it is not sent to the server in ordinary page requests. Provider failure does not roll back the published quote and enters the normal notification follow-up controls.

OTP messages deliberately do not fall back to WhatsApp because expanding an authentication secret to another channel increases exposure and requires a separately approved security design.
