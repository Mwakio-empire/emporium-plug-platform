# apps/orders/models.py

import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Order(models.Model):

    class OrderType(models.TextChoices):
        WALK_IN = 'WALK_IN', 'Walk-in POS Sale'
        ONLINE_DELIVERY = 'ONLINE_DELIVERY', 'Online Delivery'
        ONLINE_PICKUP = 'ONLINE_PICKUP', 'Online Pickup'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash Payment'
        PAYBILL = 'PAYBILL', 'M-Pesa Paybill'
        MPESA_STK = 'MPESA_STK', 'M-Pesa STK Push (Online)'
        COD = 'COD', 'Cash on Delivery/Collection'

    class Status(models.TextChoices):
        # Walk-in and shared statuses
        PENDING = 'PENDING', 'Pending Payment'
        COMPLETED = 'COMPLETED', 'Completed'
        VOIDED = 'VOIDED', 'Voided'
        # Online order statuses (Phase 2)
        PAYMENT_CONFIRMED = 'PAYMENT_CONFIRMED', 'Payment Confirmed'
        PROCESSING = 'PROCESSING', 'Processing'
        PACKING = 'PACKING', 'Packing'
        PACKED = 'PACKED', 'Packed'
        RIDER_ASSIGNED = 'RIDER_ASSIGNED', 'Rider Assigned'
        DISPATCHED = 'DISPATCHED', 'Dispatched'
        ARRIVED_AT_DESTINATION = 'ARRIVED_AT_DESTINATION', 'Arrived at Destination'
        OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for Delivery'
        READY_FOR_PICKUP = 'READY_FOR_PICKUP', 'Ready for Pickup'
        DELIVERED = 'DELIVERED', 'Delivered'
        CUSTOMER_CONFIRMED = 'CUSTOMER_CONFIRMED', 'Delivery Confirmed by Customer'
        DISPUTED = 'DISPUTED', 'Delivery Disputed'
        RETURNED = 'RETURNED', 'Returned to Branch'
        COLLECTED = 'COLLECTED', 'Collected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    order_number = models.CharField(max_length=50, unique=True, editable=False)
    branch = models.ForeignKey('branches.Branch', on_delete=models.PROTECT, related_name='orders')
    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        default=OrderType.WALK_IN,
    )

    # Customer details
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_orders',
        help_text="Null for guest/walk-in customers.",
    )
    customer_phone = models.CharField(
        max_length=15,
        help_text="Mandatory — used for SMS receipts and accountability.",
    )
    customer_email = models.EmailField(blank=True, default='')
    customer_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Walk-in customer name if no account.",
    )

    # Financials
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_payable = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Payment
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="M-Pesa receipt number or manual cash reference.",
    )
    amount_received = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Cash tender received at a walk-in POS sale.',
    )
    change_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Change returned for a walk-in cash sale.',
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    # Delivery / pickup (Phase 2 — nullable for now)
    delivery_address = models.TextField(blank=True)
    delivery_zone = models.ForeignKey(
        'logistics.DeliveryZone',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        help_text="Zone selected for delivery orders. Null for walk-in/pickup orders.",
    )
    pickup_slot = models.ForeignKey(
        'logistics.PickupSlot',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        help_text="Slot selected for pickup orders. Null for walk-in/delivery orders.",
    )
 
    pickup_code = models.CharField(max_length=10, blank=True)
    pickup_reminder_sent_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp when the 24-hour uncollected-pickup reminder SMS was sent.",
    )
    # Audit
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='processed_orders',
    )
    parcel_destination = models.ForeignKey(
        'logistics.ParcelDestination',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        help_text='Verified town collection route selected for a parcel order.',
    )
    parcel_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Chargeable product weight locked when the parcel order is created.',
    )
    parcel_county_name = models.CharField(max_length=80, blank=True)
    parcel_town = models.CharField(max_length=100, blank=True)
    parcel_collection_point = models.CharField(max_length=160, blank=True)
    parcel_operator_name = models.CharField(max_length=120, blank=True)
    pickup_expires_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Collection deadline calculated when the order becomes ready for pickup.",
    )
    pos_shift = models.ForeignKey(
        'reports.POSShift',
        on_delete=models.PROTECT,
        related_name='orders',
        null=True,
        blank=True,
        help_text='Required for new walk-in POS sales.',
    )
    void_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Mandatory audit trail reason if this order is voided.",
    )
    notes = models.TextField(blank=True)
    checkout_idempotency_key = models.UUIDField(
        unique=True, null=True, blank=True, editable=False,
    )
    checkout_request_fingerprint = models.CharField(max_length=64, blank=True, default='')
    guest_session_hash = models.CharField(max_length=64, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name='order_subtotal_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__gte=0),
                name='order_discount_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(delivery_fee__gte=0),
                name='order_delivery_fee_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(total_payable__gte=0),
                name='order_total_payable_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(amount_received__isnull=True) | models.Q(amount_received__gte=0),
                name='order_amount_received_nonnegative_or_null',
            ),
            models.CheckConstraint(
                condition=models.Q(change_due__isnull=True) | models.Q(change_due__gte=0),
                name='order_change_due_nonnegative_or_null',
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__lte=models.F('subtotal')),
                name='order_discount_not_above_subtotal',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"DNT-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_number} ({self.get_status_display()})"


class OrderItem(models.Model):
    """
    Line item on an order.

    Design rules:
    - Exactly one of `variant` or `product` must be set
    - `unit_price` is locked at purchase time — never recalculate from current product price
    - `total_price` is computed from unit_price × quantity
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')

    # Either variant or product — not both, not neither
    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='order_items',
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='order_items',
        null=True,
        blank=True,
    )

    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Price locked at the exact moment of purchase.",
    )
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, variant__isnull=True)
                    | models.Q(product__isnull=True, variant__isnull=False)
                ),
                name='order_item_exactly_one_catalog_item',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='order_item_quantity_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name='order_item_unit_price_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gte=0),
                name='order_item_total_price_nonnegative',
            ),
        ]

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        if self.variant and self.product:
            raise ValidationError("An order item cannot reference both a variant and a product.")
        if not self.variant and not self.product:
            raise ValidationError("An order item must reference either a variant or a product.")

    def full_clean(self, *args, **kwargs):
        if self.unit_price is not None and self.quantity is not None:
            self.total_price = self.unit_price * self.quantity
        super().full_clean(*args, **kwargs)

    def save(self, *args, **kwargs):
        if self.unit_price is not None and self.quantity is not None:
            self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        item = self.variant or self.product
        return f"{self.quantity}x {item} on {self.order.order_number}"


class CustomerCart(models.Model):
    """A customer's saved cart for one fulfilling branch."""

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_carts',
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='saved_customer_carts',
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'branch'],
                name='unique_customer_cart_per_branch',
            ),
        ]

    def __str__(self):
        return f"Saved cart for user {self.customer_id} at branch {self.branch_id}"


class OrderStatusHistory(models.Model):
    """
    Immutable log of every status change on every order.
    NEVER update or delete these records.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=25, blank=True)
    new_status = models.CharField(max_length=25)
    note = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='order_status_changes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Order Status History"
        verbose_name_plural = "Order Status History"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order.order_number}: {self.old_status} → {self.new_status}"
