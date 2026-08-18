# Environment-variable reference

Use `.env.example` as the safe copyable template. Real values belong in the deployment platform's secret store, never source control, screenshots, tickets or chat.

## Application and network

| Variable | Purpose | Safe local example | Deployment rule |
|---|---|---|---|
| `ENVIRONMENT` | Selects `development`, `test`, `staging` or `production` guards | `development` | Staging/production require PostgreSQL and `DEBUG=False`. |
| `SECRET_KEY` | Django signing secret | long development-only random string | At least 50 random characters when debug is off; rotate through incident procedure. |
| `DEBUG` | Debug pages and development behavior | `True` | Must be `False` outside development. |
| `ALLOWED_HOSTS` | Accepted host headers | `localhost,127.0.0.1,testserver` | Explicit hostnames; never `*`. |
| `SITE_BASE_URL` | Absolute customer links | `http://127.0.0.1:8000` | HTTPS public origin in staging/production. |
| `CSRF_TRUSTED_ORIGINS` | Trusted form origins | `http://127.0.0.1:8000` | Set the exact HTTPS origin for development tunnels too; production/staging requires at least one explicit HTTPS origin. |
| `TRUST_PROXY_HEADERS` | Trust platform HTTPS forwarding | `False` | Enable only behind the approved proxy. |
| `DATABASE_URL` | Primary database | `sqlite:///db.sqlite3` | PostgreSQL URL in staging/production. |
| `DATABASE_CONN_MAX_AGE` | Persistent DB connection lifetime | `0` locally | Tune against managed DB connection limits. |
| `REDIS_URL` | Cache, Celery broker and result backend | `redis://:local-password@127.0.0.1:56379/1` | Private authenticated/TLS URL where supported. Never commit the real password. |
| `DRF_NUM_PROXIES` | Trusted reverse-proxy count used for client-aware throttling | `0` | Set to the exact verified proxy-chain length; the Cloudflare quick-tunnel staging setup uses `1`. |
| `LOCAL_CACHE_ONLY` | In-memory cache/broker escape hatch | `True` for isolated local UI work | Rejected outside development/test. |
| `CELERY_TASK_ALWAYS_EAGER` | Execute queued tasks in the web process | `True` only for an isolated development tunnel without Redis | Rejected outside development/test; production and normal staging require Redis and separate Celery workers. |

## Business policy

| Variable | Current approved default | Meaning |
|---|---:|---|
| `PICKUP_RESERVATION_WORKING_DAYS` | `2` | Paid S18 pickup hold period; Monday-Saturday are working days. |
| `RETURN_REQUEST_WINDOW_DAYS` | `7` | Request window for explicitly eligible non-clothing goods; not automatic approval/refund. |
| `CUSTOMER_ORDER_CANCELLATION_MINUTES` | `10` | Grace period for owner-authorized cancellation of unpaid online orders before fulfilment progresses. |
| `WHATSAPP_ORDER_PHONE` | `+254116153335` | Assisted-order CTA only; WhatsApp is not the order/payment ledger. |
| `PRIVACY_CONTROLLER_NAME` | blank until approved | Legal controller identity for the privacy notice. |
| `PRIVACY_CONTACT_EMAIL` | blank until approved | Customer privacy-contact address. |
| `PRIVACY_NOTICE_APPROVED` | `False` | Production startup gate; set only after authorized approval. |

## Notifications

| Variable | Purpose | Safety rule |
|---|---|---|
| `NOTIFICATION_PROVIDER` | `console` or configured outbound provider | Production rejects `console`; development should not contact real customers. |
| `AFRICASTALKING_USERNAME` | Provider application/user | Use sandbox in non-production. |
| `AFRICASTALKING_API_KEY` | Provider credential | Secret. |
| `AFRICASTALKING_SENDER_ID` | Approved sender identity | Must be registered/accepted by provider and client. |
| `INBOUND_SMS_ENABLED` | Enables two-way callback | Leave false until dedicated number and operating procedure exist. |
| `INBOUND_SMS_WEBHOOK_TOKEN` | Callback authentication secret | At least 32 characters when enabled. |
| `WHATSAPP_FALLBACK_ENABLED` | Allows only the event allow-list | Requires business/legal approval and valid provider configuration. |
| `WHATSAPP_API_URL` / `WHATSAPP_BEARER_TOKEN` | WhatsApp provider endpoint/secret | Secrets must not appear in logs. |

## Scheduled-report email

| Variable | Purpose | Safety rule |
|---|---|---|
| `REPORT_EMAIL_ENABLED` | Enables scheduled operational-report email | Defaults false. Enable only after staging provider certification. |
| `TRANSACTIONAL_EMAIL_ENABLED` | Enables customer order and verification-code email | Defaults false locally and in staging until certification. Production refuses to start unless it is true with the SMTP backend, credentials and an approved sender. |
| `EMAIL_BACKEND` | Django email transport | Use the SMTP backend for Brevo; console locally and in-memory in tests. |
| `EMAIL_HOST` / `EMAIL_PORT` | Brevo relay endpoint | `smtp-relay.brevo.com` on port `587`. |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | Transport encryption | TLS is enabled for port 587; TLS and SSL cannot both be true. |
| `EMAIL_HOST_USER` | Brevo SMTP login | Use the SMTP login shown by Brevo, not the relay hostname. |
| `EMAIL_HOST_PASSWORD` | Brevo SMTP key | Secret; do not use an API key, account password, source file, log or screenshot. |
| `DEFAULT_FROM_EMAIL` | Verified transactional sender | Must be a valid sender on the authenticated business domain. |
| `EMAIL_TIMEOUT` | Bounded SMTP connection/send timeout | Defaults to 20 seconds. |

Follow the [Brevo scheduled-email certification runbook](../phase-10/scheduled-email-brevo.md) before enabling production schedules.

## M-Pesa

| Variable | Purpose |
|---|---|
| `MPESA_ENVIRONMENT` | Use `sandbox` for certification. Production refuses to start unless this is explicitly `production` with complete credentials and a public HTTPS callback. |
| `MPESA_CONSUMER_KEY` / `MPESA_CONSUMER_SECRET` | Daraja application credentials. |
| `MPESA_SHORTCODE` / `MPESA_PASSKEY` | STK business identity and signing input. |
| `MPESA_CALLBACK_URL` | Public HTTPS `/payments/mpesa/callback/` URL in staging/production. |

Run `python manage.py daraja_sandbox_preflight` before sandbox certification. Never use live credentials or charge a real phone during ordinary testing.

## Media, monitoring and backups

| Variables | Purpose and rule |
|---|---|
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Persistent catalog media; required by deployed fail-fast checks. |
| `USE_AWS_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME` | Optional S3-compatible static/media storage. Use least privilege. |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE` | Django/Celery error monitoring with environment/release correlation. Sampling defaults to zero until deliberately approved. |
| `SENTRY_SEND_DEFAULT_PII` | Defaults false and should remain false unless a documented privacy decision approves otherwise. |
| `ASYNC_HEARTBEAT_MAX_AGE_SECONDS` | Maximum accepted age for the combined Beat/broker/worker operational heartbeat; defaults to 600 seconds and cannot be below 120. |
| `BACKUP_ENABLED`, `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`, `BACKUP_S3_REGION`, `BACKUP_S3_KMS_KEY_ID` | Encrypted off-site logical backup. Production refuses to start unless the job and bucket are configured. It supplements and does not replace managed PITR. |
| `PG_DUMP_BINARY`, `PG_RESTORE_BINARY`, `BACKUP_PGSSLMODE`, `BACKUP_COMMAND_TIMEOUT_SECONDS` | Native PostgreSQL backup/verification binaries, required transport mode and command timeout. Deployed environments default to TLS-required backup connections. |

## HTTPS controls

`SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` control browser transport policy. Start HSTS with the configured short duration after HTTPS is proven. Do not enable include-subdomains or preload without confirming every subdomain because reversal is difficult.
