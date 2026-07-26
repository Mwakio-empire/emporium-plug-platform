# apps/payments/models.py

from django.db import models
from django.conf import settings
from .webhook_models import MpesaWebhookEvent



class MpesaTransaction(models.Model):
    """
    Tracks the full lifecycle of every Safaricom Daraja STK Push request.

    Design rules:
    - OneToOneField to Order: one order can have exactly one payment record
    - mpesa_receipt_number is the idempotency key — unique=True prevents duplicates
    - raw_callback_payload stores the full Safaricom JSON for debugging and disputes
    - confirmation_method tracks whether this was auto, manual, or fallback confirmed
    """

    class Status(models.TextChoices):
        INITIATING = 'INITIATING', 'Initiating STK Push'
        PENDING = 'PENDING', 'Pending User PIN'
        QUERY_CONFIRMED = 'QUERY_CONFIRMED', 'Provider Query Confirmed'
        RECONCILIATION_REQUIRED = 'RECONCILIATION_REQUIRED', 'Reconciliation Required'
        SUCCESS = 'SUCCESS', 'Payment Successful'
        FAILED = 'FAILED', 'Payment Failed'
        INITIATION_FAILED = 'INITIATION_FAILED', 'Initiation Failed'

    class ConfirmationMethod(models.TextChoices):
        AUTO_CALLBACK = 'AUTO_CALLBACK', 'Automatic Daraja Callback'
        MANUAL_STAFF = 'MANUAL_STAFF', 'Manual Staff Verification'
        FALLBACK_REF = 'FALLBACK_REF', 'Fallback Reference Entry'

    # OneToOne ensures one payment record per order — no duplicate payments
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.PROTECT,
        related_name='mpesa_payment',  # access as: order.mpesa_payment
    )

    merchant_request_id = models.CharField(max_length=100, unique=True, db_index=True)
    checkout_request_id = models.CharField(max_length=100, unique=True, db_index=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    expected_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    requested_phone_number = models.CharField(max_length=15, blank=True, default='')
    account_reference = models.CharField(max_length=50, blank=True, default='')
    submitted_reference = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text='Customer-entered Paybill reference; not proof of payment.',
    )
    initiation_attempts = models.PositiveSmallIntegerField(default=0)
    query_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Populated asynchronously via Safaricom callback
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    mpesa_receipt_number = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Idempotency key — Safaricom receipt reference. Unique prevents double-processing.",
    )
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    failure_reason = models.TextField(
        blank=True,
        null=True,
        help_text="ResultDesc from Safaricom if transaction was rejected.",
    )

    # Audit fields
    confirmation_method = models.CharField(
        max_length=20,
        choices=ConfirmationMethod.choices,
        blank=True,
        null=True,
        help_text="How this payment was confirmed.",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_payments',
        help_text="Staff member who manually confirmed, if applicable.",
    )
    raw_callback_payload = models.JSONField(
        null=True,
        blank=True,
        help_text="Sanitized callback evidence only; never store unnecessary personal data.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "M-Pesa Transaction"
        verbose_name_plural = "M-Pesa Transactions"
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__isnull=True) | models.Q(amount__gte=0),
                name='mpesa_amount_nonnegative_or_null',
            ),
            models.CheckConstraint(
                condition=models.Q(expected_amount__isnull=True) | models.Q(expected_amount__gte=0),
                name='mpesa_expected_amount_nonnegative_or_null',
            ),
        ]

    def __str__(self):
        return f"{self.checkout_request_id} — {self.get_status_display()}"
