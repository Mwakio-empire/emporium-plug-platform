# Daraja sandbox manual certification runbook

This procedure requires a human. Do not use production credentials, real customer data or a real charge. Use a dedicated staging deployment and Safaricom's currently documented sandbox credentials and test phone.

## Before testing

1. Deploy the exact candidate revision to staging with PostgreSQL, Redis, a web process, Celery worker and Celery Beat.
2. Use `MPESA_ENVIRONMENT=sandbox` and sandbox-only credentials.
3. Configure `MPESA_CALLBACK_URL` as the staging HTTPS URL ending in `/payments/mpesa/callback/`.
4. Confirm the callback URL is public. Do not use localhost, a private IP or a temporary URL that may expire.
5. Create a dedicated test branch, customer, product and stock. Do not reuse production records.
6. Ensure logs, Sentry and screenshots redact phones, credentials, OTPs, receipts and tokens.
7. Take a staging database snapshot before certification.

## Safe preflight

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py check --deploy
.\venv\Scripts\python.exe manage.py daraja_sandbox_preflight
```

The final command is offline. After it passes, explicitly test sandbox authentication:

```powershell
.\venv\Scripts\python.exe manage.py daraja_sandbox_preflight --network
```

This contacts only the sandbox token endpoint. It does not initiate an STK push and never prints the token.

## End-to-end scenarios

Use a new order/idempotency key unless deliberately testing duplication.

| Scenario | Expected result |
|---|---|
| Successful STK | Payment `SUCCESS`; exact amount and receipt; order `PROCESSING`; reservation consumed once. |
| Customer cancellation | Payment `FAILED`; order `CANCELLED`; reservation released once. |
| Provider rejection | Terminal failure recorded and stock released once. |
| Delayed callback | Order remains pending/query-confirmed until receipt evidence arrives; late callback settles once. |
| Query success without callback | `QUERY_CONFIRMED`; no automatic fulfilment without receipt evidence. |
| Duplicate callback replay | Inbox delivery count increases; payment, order transition and stock do not duplicate. |
| Unknown checkout ID | Callback is acknowledged and a `REVIEW_REQUIRED` event appears in Admin. |
| Identifier/amount mismatch | Payment remains unfulfilled and enters reconciliation. |
| Manual confirmation | Branch staff, manager password and reason are required; audit records are created. |
| Callback database outage | Endpoint returns HTTP 503; no false acknowledgement is issued. |

Replay only sanitized sandbox payloads. Never place a production payload or real receipt/phone in command history.

## Evidence

- `MpesaTransaction`: lifecycle, expected/received amount, receipt and confirmation method.
- `MpesaWebhookEvent`: status, outcome, delivery count and sanitized evidence.
- `OrderStatusHistory`: exactly one relevant transition.
- `StockAuditLog`: exactly one reservation consumption or release.
- `OperationalAuditRiskLog` and `AuditLog`: manager authorization and resolution.
- Worker/Beat logs: bounded polling and abandoned-payment cleanup.

Stop and preserve evidence if provider money state, order state and stock disagree. Never correct financial rows manually.

Certification passes only when all applicable scenarios have evidence, no unexplained webhook events remain open, and stock reconciles. Return the completed results template for review.
