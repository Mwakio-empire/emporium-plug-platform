from django.db import models
from django.utils import timezone


class MpesaWebhookEvent(models.Model):
    """Durable, PII-minimized inbox entry for each distinct callback payload."""

    class ProcessingStatus(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received'
        PROCESSED = 'PROCESSED', 'Processed'
        REVIEW_REQUIRED = 'REVIEW_REQUIRED', 'Review Required'
        PROCESSING_FAILED = 'PROCESSING_FAILED', 'Processing Failed'
        RESOLVED = 'RESOLVED', 'Resolved'

    payload_sha256 = models.CharField(max_length=64, unique=True, db_index=True)
    payload_size = models.PositiveIntegerField()
    delivery_count = models.PositiveIntegerField(default=1)
    payment = models.ForeignKey(
        'payments.MpesaTransaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events',
    )
    checkout_request_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    merchant_request_id = models.CharField(max_length=100, blank=True, default='')
    result_code = models.CharField(max_length=30, blank=True, default='')
    processing_status = models.CharField(
        max_length=30,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.RECEIVED,
        db_index=True,
    )
    outcome = models.CharField(max_length=50, blank=True, default='')
    review_reason = models.TextField(blank=True, default='')
    sanitized_evidence = models.JSONField(blank=True, default=dict)
    first_received_at = models.DateTimeField(auto_now_add=True)
    last_received_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resolved_mpesa_webhook_events',
    )
    resolution_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-last_received_at']
        indexes = [
            models.Index(fields=['processing_status', 'last_received_at']),
        ]

    def mark(self, *, status, outcome, reason='', evidence=None, payment=None):
        self.processing_status = status
        self.outcome = outcome
        self.review_reason = reason
        self.sanitized_evidence = evidence or {}
        if payment is not None:
            self.payment = payment
        self.processed_at = timezone.now()
        self.save(update_fields=[
            'processing_status', 'outcome', 'review_reason',
            'sanitized_evidence', 'payment', 'processed_at', 'last_received_at',
        ])

    def __str__(self):
        return f'{self.payload_sha256[:12]}: {self.get_processing_status_display()}'
