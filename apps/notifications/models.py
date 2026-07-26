from django.db import models


class Notification(models.Model):
    class Channel(models.TextChoices):
        SMS = 'SMS', 'SMS'
        WHATSAPP = 'WHATSAPP', 'WhatsApp'
        EMAIL = 'EMAIL', 'Email'

    class Criticality(models.TextChoices):
        INFORMATIONAL = 'INFORMATIONAL', 'Informational'
        IMPORTANT = 'IMPORTANT', 'Important'
        CRITICAL = 'CRITICAL', 'Critical'

    class Status(models.TextChoices):
        QUEUED = 'QUEUED', 'Queued'
        RETRY_PENDING = 'RETRY_PENDING', 'Retry Pending'
        SENT = 'SENT', 'Sent'
        SUPPRESSED = 'SUPPRESSED', 'Suppressed by Safe Provider'
        MANUAL_FOLLOWUP = 'MANUAL_FOLLOWUP', 'Manual Follow-up Required'
        RESOLVED_MANUAL = 'RESOLVED_MANUAL', 'Manually Resolved'

    event_type = models.CharField(max_length=60, db_index=True)
    template_key = models.CharField(max_length=80)
    channel = models.CharField(max_length=12, choices=Channel.choices, default=Channel.SMS)
    criticality = models.CharField(
        max_length=20, choices=Criticality.choices,
        default=Criticality.INFORMATIONAL,
    )
    recipient = models.CharField(
        max_length=254,
        help_text='Normalized delivery address. Restricted operational personal data.',
    )
    recipient_hash = models.CharField(max_length=64, db_index=True)
    branch = models.ForeignKey(
        'branches.Branch', on_delete=models.PROTECT, null=True, blank=True,
        related_name='notifications',
    )
    reference_type = models.CharField(max_length=40, blank=True, default='')
    reference_id = models.CharField(max_length=80, blank=True, default='')
    dedupe_key = models.CharField(max_length=64, unique=True)
    message_fingerprint = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    provider_message_id = models.CharField(max_length=120, blank=True, default='')
    provider_status = models.CharField(max_length=80, blank=True, default='')
    last_error_code = models.CharField(max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    followup_resolved_at = models.DateTimeField(null=True, blank=True)
    followup_resolved_by = models.ForeignKey(
        'users.User', on_delete=models.PROTECT, null=True, blank=True,
        related_name='notification_followups_resolved',
    )
    followup_resolution_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1),
                name='notification_max_attempts_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_count__lte=models.F('max_attempts')),
                name='notification_attempts_within_limit',
            ),
        ]


class NotificationDeliveryAttempt(models.Model):
    class Status(models.TextChoices):
        SENT = 'SENT', 'Sent'
        SUPPRESSED = 'SUPPRESSED', 'Suppressed by Safe Provider'
        FAILED = 'FAILED', 'Failed'

    notification = models.ForeignKey(
        Notification, on_delete=models.PROTECT, related_name='delivery_attempts',
    )
    attempt_number = models.PositiveSmallIntegerField()
    channel = models.CharField(max_length=12, choices=Notification.Channel.choices)
    provider = models.CharField(max_length=40)
    status = models.CharField(max_length=12, choices=Status.choices)
    provider_message_id = models.CharField(max_length=120, blank=True, default='')
    provider_status = models.CharField(max_length=80, blank=True, default='')
    error_code = models.CharField(max_length=80, blank=True, default='')
    response_summary = models.CharField(
        max_length=300, blank=True, default='',
        help_text='Sanitized provider metadata only; never message text or OTP values.',
    )
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-attempted_at']
        constraints = [
            models.UniqueConstraint(
                fields=['notification', 'attempt_number', 'channel'],
                name='one_notification_delivery_attempt_channel',
            ),
        ]
