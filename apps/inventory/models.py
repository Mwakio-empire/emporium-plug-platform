# apps/inventory/models.py

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Stock(models.Model):
    """
    Branch-level stock record.

    Design rules:
    - Exactly one of `product` or `variant` must be set — never both, never neither
    - Simple products (no variants) use the `product` FK
    - Products with variants use `variant` FK — one Stock row per variant per branch
    - UniqueConstraints prevent duplicate stock records per item per branch
    - Never modify quantity directly — always go through InventoryService.adjust_stock()
    """

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.CASCADE,
        related_name='stocks',
        null=True,
        blank=True,
        help_text="Set for products with variants (size, color, etc.).",
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='stocks',
        null=True,
        blank=True,
        help_text="Set for simple products with no variants.",
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='stocks',
    )
    quantity = models.PositiveIntegerField(
        default=0,
        help_text="Physical sellable units on hand, including units currently reserved.",
    )
    reserved_quantity = models.PositiveIntegerField(default=0)
    in_transit_quantity = models.PositiveIntegerField(default=0)
    damaged_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stock Records"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, variant__isnull=True)
                    | models.Q(product__isnull=True, variant__isnull=False)
                ),
                name='stock_exactly_one_catalog_item',
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__lte=models.F('quantity')),
                name='stock_reserved_not_above_on_hand',
            ),
            models.UniqueConstraint(
                fields=['product', 'branch'],
                condition=models.Q(variant__isnull=True),
                name='unique_simple_product_branch_stock',
            ),
            models.UniqueConstraint(
                fields=['variant', 'branch'],
                condition=models.Q(product__isnull=True),
                name='unique_variant_branch_stock',
            ),
        ]

    def clean(self):
        """Enforce that exactly one of product or variant is set."""
        if self.product and self.variant:
            raise ValidationError(
                "A stock record cannot be linked to both a product and a variant simultaneously."
            )
        if not self.product and not self.variant:
            raise ValidationError(
                "A stock record must be linked to either a product or a variant."
            )
        if self.reserved_quantity > self.quantity:
            raise ValidationError("Reserved stock cannot exceed physical on-hand stock.")

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    @property
    def physical_custody_quantity(self):
        return self.quantity + self.in_transit_quantity + self.damaged_quantity

    def __str__(self):
        item = self.variant or self.product
        return f"{item} @ {self.branch.name} — Qty: {self.quantity}"


class StockAuditLog(models.Model):
    """
    Immutable audit trail of every stock movement in the system.

    NEVER update or delete these records.
    Every stock change — sale, restock, adjustment, transfer, void reversal —
    creates exactly one StockAuditLog entry.
    """

    class Reason(models.TextChoices):
        SALE = 'SALE', 'Sale Completion'
        RESTOCK = 'RESTOCK', 'Restock Entry'
        CORRECTION = 'CORRECTION', 'Manual Correction'
        DAMAGE = 'DAMAGE', 'Damage Write-off'
        THEFT = 'THEFT', 'Theft Write-off'
        TRANSFER_OUT = 'TRANSFER_OUT', 'Inter-Branch Transfer Out'
        TRANSFER_IN = 'TRANSFER_IN', 'Inter-Branch Transfer In'
        REVERSAL = 'REVERSAL', 'Cancellation Reversal'
        VOID_REVERSAL = 'VOID_REVERSAL', 'Void Reversal'
        RETURN = 'RETURN', 'Customer Return'
        RESERVATION = 'RESERVATION', 'Order Reservation'
        RESERVATION_RELEASE = 'RESERVATION_RELEASE', 'Reservation Released'
        RESERVATION_CONSUMED = 'RESERVATION_CONSUMED', 'Reservation Consumed'
        DAMAGE_QUARANTINE = 'DAMAGE_QUARANTINE', 'Moved to Damaged Quarantine'

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='audit_logs',
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='audit_logs',
        null=True,
        blank=True,
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='audit_logs',
    )
    change_amount = models.IntegerField(
        help_text="Positive = stock added. Negative = stock removed.",
    )
    running_total = models.PositiveIntegerField(
        help_text="Stock balance immediately after this change was applied.",
    )
    reserved_total = models.PositiveIntegerField(default=0)
    in_transit_total = models.PositiveIntegerField(default=0)
    damaged_total = models.PositiveIntegerField(default=0)
    reason = models.CharField(max_length=30, choices=Reason.choices, db_index=True)
    note = models.TextField(
        blank=True,
        default='',
        help_text="Required context for manual adjustments (corrections, damage, theft).",
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Order number, transfer ID, or other reference.",
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='stock_actions',
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Stock Audit Log"
        verbose_name_plural = "Stock Audit Logs"
        ordering = ['-timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'product', 'reason', 'reference_number'],
                condition=models.Q(
                    product__isnull=False,
                    reference_number__isnull=False,
                    reason__in=[
                        'RESERVATION', 'RESERVATION_RELEASE',
                        'RESERVATION_CONSUMED', 'TRANSFER_OUT', 'TRANSFER_IN',
                        'CORRECTION', 'THEFT', 'DAMAGE_QUARANTINE',
                    ],
                ),
                name='unique_product_state_movement_reference',
            ),
            models.UniqueConstraint(
                fields=['branch', 'variant', 'reason', 'reference_number'],
                condition=models.Q(
                    variant__isnull=False,
                    reference_number__isnull=False,
                    reason__in=[
                        'RESERVATION', 'RESERVATION_RELEASE',
                        'RESERVATION_CONSUMED', 'TRANSFER_OUT', 'TRANSFER_IN',
                        'CORRECTION', 'THEFT', 'DAMAGE_QUARANTINE',
                    ],
                ),
                name='unique_variant_state_movement_reference',
            ),
        ]

    def __str__(self):
        item = self.variant or self.product
        direction = '+' if self.change_amount > 0 else ''
        return (
            f"{item} | {self.branch.name} | "
            f"{direction}{self.change_amount} | "
            f"Balance: {self.running_total} | "
            f"{self.get_reason_display()}"
        )

class TransferRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'PENDING', 'Requested - Awaiting Source Approval'
        APPROVED = 'APPROVED', 'Approved for Dispatch'
        DISPATCHED = 'DISPATCHED', 'Dispatched / In Transit'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially Received'
        RECEIVED = 'RECEIVED', 'Received at Destination'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled by Requester'

    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='transfer_requests', null=True, blank=True)
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.PROTECT, related_name='transfer_requests', null=True, blank=True)
    quantity = models.PositiveIntegerField()
    from_branch = models.ForeignKey('branches.Branch', on_delete=models.PROTECT, related_name='transfers_out')
    to_branch = models.ForeignKey('branches.Branch', on_delete=models.PROTECT, related_name='transfers_in')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='transfer_requests_made')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='transfer_requests_approved', null=True, blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='transfer_requests_confirmed', null=True, blank=True)
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='transfer_requests_dispatched', null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='transfer_requests_cancelled', null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    received_quantity = models.PositiveIntegerField(default=0)
    rejection_reason = models.TextField(blank=True, default='')
    cancellation_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-requested_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, variant__isnull=True)
                    | models.Q(product__isnull=True, variant__isnull=False)
                ),
                name='transfer_exactly_one_catalog_item',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='transfer_quantity_positive',
            ),
            models.CheckConstraint(
                condition=~models.Q(from_branch=models.F('to_branch')),
                name='transfer_branches_must_differ',
            ),
            models.CheckConstraint(
                condition=models.Q(received_quantity__lte=models.F('quantity')),
                name='transfer_received_not_above_requested',
            ),
        ]
        indexes = [
            models.Index(fields=['to_branch', 'status']),
            models.Index(fields=['from_branch', 'status']),
        ]

    def clean(self):
        if self.product and self.variant:
            raise ValidationError("A transfer cannot reference both a product and a variant.")
        if not self.product and not self.variant:
            raise ValidationError("A transfer must reference either a product or a variant.")
        if self.from_branch_id and self.to_branch_id and self.from_branch_id == self.to_branch_id:
            raise ValidationError("from_branch and to_branch cannot be identical.")

    @property
    def remaining_quantity(self):
        return self.quantity - self.received_quantity

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        item = self.variant or self.product
        return f"Transfer #{self.id}: {self.quantity}x {item} [{self.from_branch}→{self.to_branch}] ({self.status})"


class TransferReceipt(models.Model):
    """Immutable evidence for each full or partial transfer receipt."""

    transfer = models.ForeignKey(
        TransferRequest, on_delete=models.PROTECT, related_name='receipts',
    )
    quantity = models.PositiveIntegerField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='transfer_receipts_recorded',
    )
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['received_at', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='transfer_receipt_quantity_positive',
            ),
        ]


class StockIntake(models.Model):
    """One supplier delivery booked into an authorized receiving hub."""

    branch = models.ForeignKey(
        'branches.Branch', on_delete=models.PROTECT, related_name='stock_intakes',
    )
    supplier_name = models.CharField(max_length=150)
    delivery_reference = models.CharField(max_length=100)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='stock_intakes_received',
    )
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-received_at']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'delivery_reference'],
                name='unique_supplier_delivery_reference_per_branch',
            ),
        ]


class StockIntakeLine(models.Model):
    intake = models.ForeignKey(
        StockIntake, on_delete=models.PROTECT, related_name='lines',
    )
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_intake_lines',
    )
    variant = models.ForeignKey(
        'catalog.ProductVariant', on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_intake_lines',
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, variant__isnull=True)
                    | models.Q(product__isnull=True, variant__isnull=False)
                ),
                name='intake_line_exactly_one_catalog_item',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='intake_line_quantity_positive',
            ),
            models.UniqueConstraint(
                fields=['intake', 'product'],
                condition=models.Q(variant__isnull=True),
                name='unique_simple_product_intake_line',
            ),
            models.UniqueConstraint(
                fields=['intake', 'variant'],
                condition=models.Q(product__isnull=True),
                name='unique_variant_intake_line',
            ),
        ]


class StockCount(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    branch = models.ForeignKey(
        'branches.Branch', on_delete=models.PROTECT, related_name='stock_counts',
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.OPEN, db_index=True,
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='stock_counts_started',
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_counts_completed',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_counts_cancelled',
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    cancellation_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']
        constraints = [
            models.UniqueConstraint(
                fields=['branch'], condition=models.Q(status='OPEN'),
                name='unique_open_stock_count_per_branch',
            ),
        ]


class StockCountLine(models.Model):
    stock_count = models.ForeignKey(
        StockCount, on_delete=models.PROTECT, related_name='lines',
    )
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_count_lines',
    )
    variant = models.ForeignKey(
        'catalog.ProductVariant', on_delete=models.PROTECT, null=True, blank=True,
        related_name='stock_count_lines',
    )
    expected_quantity = models.PositiveIntegerField()
    counted_quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, variant__isnull=True)
                    | models.Q(product__isnull=True, variant__isnull=False)
                ),
                name='stock_count_line_exactly_one_item',
            ),
            models.UniqueConstraint(
                fields=['stock_count', 'product'],
                condition=models.Q(variant__isnull=True),
                name='unique_simple_product_stock_count_line',
            ),
            models.UniqueConstraint(
                fields=['stock_count', 'variant'],
                condition=models.Q(product__isnull=True),
                name='unique_variant_stock_count_line',
            ),
        ]

    @property
    def variance(self):
        if self.counted_quantity is None:
            return None
        return self.counted_quantity - self.expected_quantity


class LowStockAlertState(models.Model):
    """Durable edge-trigger state preventing repeated low-stock alert spam."""

    stock = models.OneToOneField(
        Stock, on_delete=models.CASCADE, related_name='low_stock_alert_state',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    first_triggered_at = models.DateTimeField(auto_now_add=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
