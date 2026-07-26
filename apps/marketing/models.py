from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db.models import F, Q

class Coupon(models.Model):
    """
    Structural promotional logic managing usage-capped discount vouchers,
    minimum order value constraints, and strict temporal execution lifecycles.
    """
    class DiscountType(models.TextChoices):
        FIXED = 'FIXED', 'Fixed Amount (KES)'
        PERCENTAGE = 'PERCENTAGE', 'Percentage Reduction (%)'

    code = models.CharField(
        max_length=50, 
        unique=True, 
        db_index=True, 
        help_text="Unique tokenized alphanumeric string used at checkout."
    )
    discount_type = models.CharField(
        max_length=20, 
        choices=DiscountType.choices, 
        default=DiscountType.FIXED
    )
    value = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(0.01)],
        help_text="The raw value or percentage rate of the discount campaign."
    )
    active_from = models.DateTimeField(help_text="Timestamp defining the active start window.")
    active_to = models.DateTimeField(help_text="Timestamp defining the campaign expiration point.")
    usage_limit = models.PositiveIntegerField(help_text="Maximum total number of times this coupon can be globally claimed.")
    per_customer_limit = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Maximum successful redemptions by one authenticated customer.",
    )
    times_used = models.PositiveIntegerField(
        default=0, 
        help_text="The current running count of successful allocations logged across checkouts."
    )
    min_order_value = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00, 
        validators=[MinValueValidator(0.00)],
        help_text="Minimum cart subtotal required before this voucher becomes applicable."
    )
    branches = models.ManyToManyField(
        'branches.Branch', blank=True, related_name='coupons',
        help_text="Leave empty for all branches.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

   
    class Meta:
        verbose_name = "Coupon"
        verbose_name_plural = "Coupons"
        constraints = [
            models.CheckConstraint(condition=Q(active_to__gt=F('active_from')), name='coupon_window_valid'),
            models.CheckConstraint(condition=Q(times_used__lte=F('usage_limit')), name='coupon_usage_within_limit'),
            models.CheckConstraint(
                condition=Q(discount_type='FIXED') | Q(value__lte=100),
                name='coupon_percentage_not_above_100',
            ),
        ]

    def clean(self):
        super().clean()
        self.code = str(self.code or '').strip().upper()
        if self.active_from and self.active_to and self.active_to <= self.active_from:
            raise ValidationError({'active_to': 'Coupon end time must be after its start time.'})
        if self.discount_type == self.DiscountType.PERCENTAGE and self.value > 100:
            raise ValidationError({'value': 'Percentage discounts cannot exceed 100%.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} ({self.discount_type})"


class CouponRedemption(models.Model):
    """Immutable evidence that one order consumed one coupon allocation."""

    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name='redemptions')
    order = models.OneToOneField(
        'orders.Order', on_delete=models.PROTECT, related_name='coupon_redemption',
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='coupon_redemptions',
    )
    customer_key = models.CharField(
        max_length=64, db_index=True,
        help_text="Keyed digest used for authenticated and guest per-customer limits.",
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)],
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['coupon', 'order'], name='unique_coupon_order_redemption'),
        ]


class FlashSale(models.Model):
    """
    Real-time promotional scheduling tool overriding product base variant costs
    within highly restrictive temporal windows.
    """
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.CASCADE, related_name='flash_sales')
    sale_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(0.01)],
        help_text="Promotional unit pricing active during the campaign slot."
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(
        default=True, 
        help_text="Administrative toggle to manually deprecate or suspend the flash campaign."
    )
    class Meta:
        verbose_name = "Flash Sale Campaign"
        verbose_name_plural = "Flash Sale Campaigns"
        constraints = [
            models.CheckConstraint(condition=Q(end_time__gt=F('start_time')), name='flash_sale_window_valid'),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': 'Flash-sale end time must be after its start time.'})
        if self.variant_id:
            base_price = self.variant.effective_price
            if self.sale_price >= base_price:
                raise ValidationError({'sale_price': 'Flash-sale price must be below the normal price.'})
            overlaps = FlashSale.objects.filter(
                variant_id=self.variant_id,
                is_active=True,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(pk=self.pk)
            if self.is_active and overlaps.exists():
                raise ValidationError('This variant already has an overlapping active flash sale.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Flash Sale: {self.variant} at KES {self.sale_price}"



class ProductReview(models.Model):
    """
    Maintains moderated product reviews linked to customer purchase history.
    """
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='product_reviews')
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Customer evaluation rank scored strictly between 1 and 5 stars."
    )
    comment = models.TextField(help_text="Descriptive textural evaluation left by the customer.")
    is_verified_purchase = models.BooleanField(
        default=False, 
        help_text="Automatically verified true if the client has an accomplished order record for this item."
    )
    is_approved = models.BooleanField(
        default=False, 
        help_text="Moderation control handle. Only approved evaluations render on the public storefront layout."
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='reviews_moderated',
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_reason = models.TextField(blank=True, default='')
    is_current = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Product Review"
        verbose_name_plural = "Product Reviews"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'customer'], condition=Q(is_current=True),
                name='one_current_review_per_customer_product',
            ),
        ]

    def __str__(self):
        return f"Review ({self.rating} Stars) by {self.customer.username}"


class ReturnRequest(models.Model):
    """
    Tracks item-return requests that require management review.
    """
    class ReturnStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Evaluation'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    class ItemCondition(models.TextChoices):
        UNOPENED = 'UNOPENED', 'Unopened'
        GOOD = 'GOOD', 'Good / Resellable'
        DAMAGED = 'DAMAGED', 'Damaged'
        DEFECTIVE = 'DEFECTIVE', 'Defective'
        UNKNOWN = 'UNKNOWN', 'Not Yet Assessed'

    class StockDisposition(models.TextChoices):
        SELLABLE = 'SELLABLE', 'Return to Sellable Stock'
        DAMAGED = 'DAMAGED', 'Damaged Stock'
        QUARANTINED = 'QUARANTINED', 'Quarantine for Further Assessment'

    class RefundStatus(models.TextChoices):
        NOT_REQUIRED = 'NOT_REQUIRED', 'No Refund Required'
        PENDING_MANUAL = 'PENDING_MANUAL', 'Pending Manual Refund'
        COMPLETED_MANUAL = 'COMPLETED_MANUAL', 'Manually Refunded'
        DECLINED = 'DECLINED', 'Refund Declined'

    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='return_requests')
    order_item = models.ForeignKey('orders.OrderItem', on_delete=models.PROTECT, related_name='returned_items')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    reason = models.TextField(help_text="Mandatory client statement highlighting the reason for the item rejection.")
    status = models.CharField(
        max_length=20, 
        choices=ReturnStatus.choices, 
        default=ReturnStatus.PENDING,
        db_index=True
    )
    item_condition = models.CharField(
        max_length=20, choices=ItemCondition.choices,
        default=ItemCondition.UNKNOWN,
    )
    stock_disposition = models.CharField(
        max_length=20, choices=StockDisposition.choices,
        blank=True, default='',
    )
    refund_status = models.CharField(
        max_length=20, choices=RefundStatus.choices,
        default=RefundStatus.NOT_REQUIRED, db_index=True,
    )
    decision_reason = models.TextField(blank=True, default='')
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='return_decisions',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

      
    class Meta:
        verbose_name = "Return Request"
        verbose_name_plural = "Return Requests"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='return_quantity_positive'),
            models.CheckConstraint(
                condition=Q(status='PENDING') | Q(decided_at__isnull=False),
                name='final_return_has_decision_time',
            ),
        ]
        

    def __str__(self):
        return f"Return Request #{self.id} ({self.status})"
