# Scheduled-report email: Brevo staging certification

Status: local implementation verified; one controlled Brevo staging send is required before this remediation item and production email can be approved.

## Why Brevo SMTP

The application already uses Django's standard email interface, so Brevo SMTP adds a transactional provider without a provider-specific application dependency. Brevo's [official SMTP configuration guide](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP) documents the relay, SMTP login and SMTP key, while its [port guidance](https://help.brevo.com/hc/en-us/articles/10905415650322-Which-SMTP-port-should-I-use-Port-587-465-or-2525) recommends port 587 for TLS. The key is not an API key or account password.

## Safety boundaries

- Use staging, synthetic report data and an authorized tester inbox.
- Do not email real customer, staff-sales or production financial data.
- Never paste the SMTP key into source control, screenshots, tickets, test evidence or chat.
- A timeout or worker crash after provider acceptance is ambiguous. `PROCESSING` and `FAILED` outcomes must be investigated rather than blindly retried.
- Keep `REPORT_EMAIL_ENABLED=False` in production until staging evidence is accepted.

## Account and domain preparation

1. Create or approve the client-owned Brevo account; do not bind the service permanently to a developer's personal account.
2. Add the business domain and complete Brevo's domain authentication instructions.
3. Publish and verify SPF, DKIM and the client-approved DMARC policy with the domain administrator.
4. Create a transactional sender such as `reports@<client-domain>` and verify it in Brevo.
5. In Brevo SMTP settings, create a dedicated SMTP key for this application and copy it once into the staging secret store.

## Staging variables

Configure these on the staging web, worker and Beat services through their shared environment group:

```text
REPORT_EMAIL_ENABLED=True
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=<Brevo SMTP login>
EMAIL_HOST_PASSWORD=<Brevo SMTP key>
DEFAULT_FROM_EMAIL=reports@<authenticated-client-domain>
EMAIL_TIMEOUT=20
```

The SMTP login is the value Brevo displays for SMTP authentication. Do not substitute the relay hostname, an API key or the Brevo account password.

## Controlled acceptance test

1. Deploy the exact reviewed Git revision to staging with synthetic data only.
2. Run `python manage.py check`. Any `reports.E001` result blocks the test.
3. Confirm one worker and exactly one Beat instance are healthy.
4. As Super Admin, create one daily `ScheduledReport` for an authorized tester inbox, a synthetic branch and a `next_run_at` in the past.
5. Wait for the hourly dispatcher or invoke `send_scheduled_report.delay(<schedule-id>)` once from the staging Django shell.
6. Confirm exactly one `ScheduledReportDelivery` exists for the period and moves from `PROCESSING` to `SENT`.
7. Confirm the tester receives exactly one email from the verified sender, the PDF opens, the stated period is correct and its totals match the synthetic source orders.
8. Confirm `last_sent_at` is set and `next_run_at` advances once.
9. Invoke the same task ID again. Confirm no second email is sent.
10. Retain the revision, environment, schedule/delivery IDs, timestamps, Brevo message outcome and redacted screenshots. Do not retain the SMTP key or report customer data.

## Failure-path test

1. Keep synthetic data and use a separate test schedule.
2. Temporarily disable `REPORT_EMAIL_ENABLED` in staging and run the due task once.
3. Confirm the task returns failure without sending, records `FAILED` with `ImproperlyConfigured`, and advances the schedule once for manual follow-up.
4. Restore the approved settings and redeploy. Do not alter a failed period to force an automatic retry; create a new controlled schedule/period after investigating.

## Approval evidence

Record the tester, date/time, Git revision, staging URL, sender domain, recipient owner, delivery record, Brevo outcome, PDF reconciliation result, duplicate-send result and failure-path result. Client/technical approval is required before copying credentials or enabling schedules in production.
