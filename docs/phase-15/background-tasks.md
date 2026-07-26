# Background-task schedule and ownership

Celery uses Redis in deployed environments. Exactly one Beat process owns schedules. All times use `Africa/Nairobi`.

## Beat schedule

| Minute/time | Task | Purpose | Operational alert |
|---|---|---|---|
| Every 5 minutes | `orders.cancel_abandoned_pending_orders` | Cancel unpaid STK orders after the configured timeout and release reservations once. | Alert on repeated per-order failures or growing pending backlog. |
| Hourly at `:00` | `inventory.send_branch_low_stock_alerts` | Detect low-stock transitions and suppress repeated alerts until recovery. | Alert when task is missing for more than two intervals. |
| Hourly at `:05` | `reports.tasks.dispatch_due_scheduled_reports` | Dispatch only active, configured and due schedules. | `PROCESSING` prevents blind duplicate sends; `FAILED` requires manual follow-up. Enable email only after provider certification. |
| Hourly at `:15` | `orders.send_pickup_reminders` | Send one reminder after 24 hours in ready-for-pickup. | Review queue/provider failure; do not resend blindly. |
| Hourly at `:45` | `orders.auto_cancel_unresolved_pickups` | Cancel expired pickups and release stock exactly once. | Escalate any stock reversal failure. |
| Daily 03:00 | `users.purge_unverified_accounts` | Remove inactive, never-verified customer signups older than 24 hours. | Alert if task stops or encounters protected records. |

Backups are deliberately not scheduled in Beat. Production uses one platform scheduler invoking `manage.py create_database_backup`, while managed PostgreSQL PITR remains mandatory.

## Event-driven tasks

- M-Pesa pending-status polling is queued after STK initiation and uses bounded retries.
- Notification tasks persist a deduplicated event/attempt before contacting a provider.
- Order, payment, pickup, delivery, transfer, low-stock, void and shift-variance messages are queued after the relevant transaction commits.
- Report delivery records an outcome and manual follow-up obligation.

## Operator checks

Monitor worker heartbeat, Beat heartbeat, queue depth, oldest queued task, retry/exhaustion count and scheduled-task last-success time. A queue call failure must not roll back a completed order/inventory transition; it creates an operational follow-up instead.
