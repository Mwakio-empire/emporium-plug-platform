from django.db import models

# Create your models here.
from django.db import models
from django.conf import settings
from branches.models import Branch


class POSShift(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='pos_shifts')
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='pos_shifts',
    )
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-opened_at']
        constraints = [
            models.UniqueConstraint(
                fields=['cashier'],
                condition=models.Q(status='OPEN'),
                name='one_open_pos_shift_per_cashier',
            ),
            models.CheckConstraint(
                condition=models.Q(opening_cash__gte=0),
                name='pos_shift_opening_cash_nonnegative',
            ),
        ]

    def __str__(self):
        return f'{self.cashier} at {self.branch} ({self.status})'

class ShiftReconciliation(models.Model):
    """
    Maintains financial control records tracking physical cash drawer 
    closings against expected running system aggregates per branch shift.
    """
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='shift_reconciliations')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='closed_shifts')
    pos_shift = models.OneToOneField(
        POSShift,
        on_delete=models.PROTECT,
        related_name='reconciliation',
        null=True,
        blank=True,
    )
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(auto_now_add=True)
    
    # Financial metrics
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2)
    actual_cash = models.DecimalField(max_digits=12, decimal_places=2)
    cash_variance = models.DecimalField(max_digits=12, decimal_places=2, help_text="Calculated as actual_cash - expected_cash")
    mpesa_total_settled = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    notes = models.TextField(blank=True, null=True)
    is_verified_by_manager = models.BooleanField(default=False)
    requires_manager_review = models.BooleanField(default=False, db_index=True)
    verification_reason = models.TextField(blank=True, default='')
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='verified_shifts'
    )

    class Meta:
        ordering = ['-closed_at']
        indexes = [
            models.Index(fields=['branch', 'closed_at']),
            models.Index(fields=['cashier', 'closed_at']),
        ]

    def save(self, *from_kwargs, **kwargs):
        # Programmatically guarantee mathematical consistency
        self.cash_variance = self.actual_cash - self.expected_cash
        super().save(*from_kwargs, **kwargs)

    def __str__(self):
        return f"Shift Close {self.branch.name} - {self.closed_at.strftime('%Y-%m-%d')} (Variance: {self.cash_variance})"


class OperationalAuditRiskLog(models.Model):
    """
    Central operational compliance model tracking high-risk staff operations
    such as order voids, manual reference confirmations, and unauthorized security bypasses.
    """
    class RiskSeverity(models.TextChoices):
        LOW = 'LOW', 'Low Operational Risk'
        MEDIUM = 'MEDIUM', 'Medium Auditable Risk'
        HIGH = 'HIGH', 'High Security Warning'
        CRITICAL = 'CRITICAL', 'Critical System Exception'

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='audit_risk_logs', null=True, blank=True)
    initiator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='triggered_audit_logs')
    action_type = models.CharField(max_length=100, db_index=True, help_text="e.g., ORDER_VOID, MANUAL_MPESA_MATCH, PRICE_OVERRIDE")
    severity = models.CharField(max_length=15, choices=RiskSeverity.choices, default=RiskSeverity.LOW)
    target_record_id = models.CharField(max_length=50, blank=True, null=True, help_text="Reference key to target object")
    justification_trail = models.TextField(help_text="Mandatory textual reason specified during override actions")
    metadata_payload = models.JSONField(blank=True, null=True, help_text="Captures relevant system state variables")

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.severity}] {self.action_type} by User ID {self.initiator.id} at {self.timestamp}"


class ScheduledReport(models.Model):
    class Frequency(models.TextChoices):
        DAILY = 'DAILY', 'Daily'
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'

    name = models.CharField(max_length=120)
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, null=True, blank=True,
        related_name='scheduled_reports',
        help_text='Leave empty only for an authorized all-branch report.',
    )
    recipient_email = models.EmailField()
    is_active = models.BooleanField(default=True, db_index=True)
    next_run_at = models.DateTimeField(db_index=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='report_schedules_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['next_run_at', 'name']

    def __str__(self):
        return f'{self.name} -> {self.recipient_email}'


class ScheduledReportDelivery(models.Model):
    class Status(models.TextChoices):
        PROCESSING = 'PROCESSING', 'Processing - Do Not Retry'
        SENT = 'SENT', 'Sent'
        FAILED = 'FAILED', 'Failed - Manual Follow-up Required'

    schedule = models.ForeignKey(
        ScheduledReport, on_delete=models.PROTECT, related_name='deliveries',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    attempted_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['-attempted_at']
        constraints = [
            models.UniqueConstraint(
                fields=['schedule', 'period_start', 'period_end'],
                name='one_scheduled_report_delivery_per_period',
            ),
        ]
