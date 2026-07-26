# Notification event catalog

| Event | Template key | Class | Default channel | WhatsApp fallback |
|---|---|---|---|---|
| OTP | `security.otp` | Critical | SMS | No |
| Order placed | `order.placed` | Important | SMS | No |
| Payment confirmed | `payment.confirmed` | Critical | SMS | Allowed only when globally enabled |
| Walk-in receipt | `pos.receipt` | Important | SMS | No |
| Order cancelled | `order.cancelled` | Important | SMS | No |
| Delivery status | `delivery.status` | Important | SMS | No |
| Pickup ready | `pickup.ready` | Important | SMS | No |
| Pickup reminder | `pickup.reminder` | Important | SMS | No |
| Collection confirmed | `pickup.collected` | Informational | SMS | No |
| Delivery dispute | `delivery.dispute` | Critical | SMS | Allowed only when globally enabled |
| Low stock | `inventory.low_stock` | Important | SMS | No |
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

OTP messages deliberately do not fall back to WhatsApp because expanding an authentication secret to another channel increases exposure and requires a separately approved security design.
