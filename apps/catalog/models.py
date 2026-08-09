
import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField
from .validators import validate_catalog_image

class Category(models.Model):
    """
    Self-referential adjacency list model allowing infinite category nesting.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='subcategories',
        help_text="Leave blank if this is a top-level root category."
    )
    is_visible = models.BooleanField(
        default=True, 
        help_text="Toggle to control public visibility on the storefront."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        # Generates a clear representation path: e.g., "Electronics > Phones > Smartphones"
        full_path = [self.name]
        k = self.parent
        while k is not None:
            full_path.append(k.name)
            k = k.parent
        return ' > '.join(reversed(full_path))


class Product(models.Model):
    """
    Core Product Definition blueprint containing fields managed explicitly by Admin/Managers.
    """
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        HIDDEN = 'HIDDEN', 'Hidden'
        OUT_OF_STOCK = 'OUT_OF_STOCK', 'Out of Stock'

    class CustomerReturnPolicy(models.TextChoices):
        SUPPORT_ONLY = 'SUPPORT_ONLY', 'Contact support'
        SEVEN_DAY = 'SEVEN_DAY', '7-day return requests'

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="Optional search-result description. Falls back to the product description.",
    )
    specifications = models.JSONField(
        default=dict,
        blank=True,
        help_text="Customer-facing specification names and values, for example material or warranty.",
    )
    sku = models.CharField(
        max_length=50, 
        unique=True, 
        blank=True, 
        help_text="Auto-generated unique inventory unit identification identifier."
    )
    category = models.ForeignKey(
        Category, 
        on_delete=models.PROTECT, 
        related_name='products'
    )
    image = CloudinaryField(
        'image', blank=True, null=True, folder='catalog_products/',
        validators=[validate_catalog_image],
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        help_text="Base unit price. Staff are explicitly blocked from modifying this."
    )
    compare_at_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        help_text="Strike-through price used for rendering active discount thresholds."
    )
    weight = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0.00, 
        help_text="Weight metrics captured in kilograms for logistical fulfillment updates."
    )
    dimensions = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        help_text="Structural volume boundary tracking (L x W x H in cm)."
    )
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.ACTIVE
    )
    customer_return_policy = models.CharField(
        max_length=20,
        choices=CustomerReturnPolicy.choices,
        default=CustomerReturnPolicy.SUPPORT_ONLY,
        help_text=(
            'Controls customer self-service requests. Keep clothing/fashion and '
            'unclassified goods on Contact support; explicitly enable eligible '
            'non-clothing goods.'
        ),
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5, 
        help_text="Triggers an automated alert when available quantities dip past this marker."
    )
    minimum_order_quantity = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Minimum units of this product required at checkout. Quantities across "
            "its sizes, colours and other variants are combined."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minimum_order_quantity__gte=1),
                name='product_minimum_order_quantity_positive',
            ),
        ]

    def save(self, *args, **kwargs):
        # Clean production-grade safe SKU generation protocol
        if not self.sku:
            prefix = self.category.name[:3].upper() if self.category else "PRD"
            unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
            self.sku = f"{prefix}-{unique_suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class QuantityPriceTier(models.Model):
    """An optional product-level bulk discount shared by all variants."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='quantity_price_tiers',
    )
    minimum_quantity = models.PositiveIntegerField(
        help_text='Combined product quantity required before this discount applies.',
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='Percentage deducted from each item’s regular unit price.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('minimum_quantity', 'id')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minimum_quantity__gte=2),
                name='quantity_tier_minimum_at_least_two',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(discount_percentage__gt=0)
                    & models.Q(discount_percentage__lt=100)
                ),
                name='quantity_tier_discount_between_zero_and_hundred',
            ),
            models.UniqueConstraint(
                fields=('product', 'minimum_quantity'),
                name='unique_product_quantity_tier_threshold',
            ),
        ]
        indexes = [
            models.Index(
                fields=('product', 'is_active', 'minimum_quantity'),
                name='catalog_qty_tier_lookup_idx',
            ),
        ]

    def __str__(self):
        return (
            f'{self.product.name}: {self.minimum_quantity}+ units, '
            f'{self.discount_percentage}% off'
        )


class ProductOption(models.Model):
    """A customer-selectable product dimension such as Size or Colour."""

    class DisplayType(models.TextChoices):
        BUTTON = 'BUTTON', 'Buttons'
        COLOUR = 'COLOUR', 'Colour swatches'
        DROPDOWN = 'DROPDOWN', 'Dropdown'

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='options')
    name = models.CharField(max_length=50)
    display_type = models.CharField(
        max_length=10, choices=DisplayType.choices, default=DisplayType.BUTTON,
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'name'], name='unique_product_option_name',
            ),
        ]

    def __str__(self):
        return f'{self.product.name} — {self.name}'


class ProductOptionValue(models.Model):
    """One allowed value inside a product option group."""

    option = models.ForeignKey(ProductOption, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=50)
    colour_hex = models.CharField(
        max_length=7, blank=True, default='',
        help_text='Optional six-digit colour, for example #1F2937.',
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['option', 'value'], name='unique_product_option_value',
            ),
        ]

    def clean(self):
        super().clean()
        if self.colour_hex:
            value = self.colour_hex.upper()
            if len(value) != 7 or value[0] != '#' or any(
                character not in '0123456789ABCDEF' for character in value[1:]
            ):
                raise ValidationError({'colour_hex': 'Use a colour in #RRGGBB format.'})
            self.colour_hex = value

    def __str__(self):
        return f'{self.option.name}: {self.value}'


class ProductVariant(models.Model):
    """
    Sub-product variations tracking combinations like size, color, or custom fields.
    """
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='variants'
    )
    sku = models.CharField(max_length=80, unique=True, blank=True)
    image = CloudinaryField(
        'image', blank=True, null=True, folder='catalog_products/variants/',
        validators=[validate_catalog_image],
    )
    is_active = models.BooleanField(default=True)
    combination_signature = models.CharField(max_length=255, blank=True, default='')
    attribute_name = models.CharField(max_length=50, help_text="e.g., Size, Color")
    attribute_value = models.CharField(max_length=50, help_text="e.g., Large, Crimson Red")
    option_values = models.ManyToManyField(
        ProductOptionValue,
        through='VariantOptionAssignment',
        related_name='variants',
        blank=True,
    )
    price_override = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        help_text="Optional variant-specific overriding price tier."
    )

    class Meta:
        verbose_name = "Product Variant"
        verbose_name_plural = "Product Variants"
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'attribute_name', 'attribute_value'],
                name='unique_legacy_product_variant_label',
            ),
            models.UniqueConstraint(
                fields=['product', 'combination_signature'],
                condition=~models.Q(combination_signature=''),
                name='unique_product_variant_combination',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f'{self.product.sku}-V{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        # Fall back to global base price context if an item variant doesn't require separate price rules
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def option_summary(self):
        values = list(self.option_values.select_related('option').order_by(
            'option__position', 'option_id', 'position', 'id',
        ))
        if values:
            return ' / '.join(f'{value.option.name}: {value.value}' for value in values)
        return f'{self.attribute_name}: {self.attribute_value}'

    def __str__(self):
        return f'{self.product.name} ({self.option_summary})'


class VariantOptionAssignment(models.Model):
    """Links one variant SKU to one value from each of its option groups."""

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name='option_assignments',
    )
    option = models.ForeignKey(ProductOption, on_delete=models.PROTECT)
    value = models.ForeignKey(ProductOptionValue, on_delete=models.PROTECT)

    class Meta:
        ordering = ['option__position', 'option_id']
        constraints = [
            models.UniqueConstraint(
                fields=['variant', 'option'], name='unique_variant_option_assignment',
            ),
            models.UniqueConstraint(
                fields=['variant', 'value'], name='unique_variant_option_value',
            ),
        ]

    def clean(self):
        super().clean()
        if self.value_id and self.option_id and self.value.option_id != self.option_id:
            raise ValidationError({'value': 'The selected value does not belong to this option.'})
        if self.variant_id and self.option_id and self.variant.product_id != self.option.product_id:
            raise ValidationError({'option': 'The option must belong to the variant product.'})

    def __str__(self):
        return f'{self.variant.sku} — {self.option.name}: {self.value.value}'


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='gallery_images',
    )
    image = CloudinaryField(
        'image', folder='catalog_products/gallery/',
        validators=[validate_catalog_image],
    )
    alt_text = models.CharField(
        max_length=255,
        help_text="Describe the visible product image for customers using screen readers.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'sort_order'],
                name='unique_product_gallery_sort_order',
            ),
        ]

    def __str__(self):
        return f"{self.product.name} image {self.sort_order}"


class WishlistItem(models.Model):
    """A customer's saved product; wishlists never reserve inventory."""

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlist_items',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='wishlisted_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'product'],
                name='unique_customer_wishlist_product',
            ),
        ]

    def __str__(self):
        return f"{self.customer_id} saved {self.product_id}"


class RestockSubscriptionManager(models.Manager):
    def create_for_target(self, *, phone_number, product=None, variant=None, customer=None):
        from notifications.services import keyed_digest, normalize_phone

        phone = normalize_phone(phone_number)
        now = timezone.now()
        target_filter = {'variant': variant} if variant is not None else {'product': product}
        self.filter(
            **target_filter,
            phone_hash=keyed_digest(phone),
            status=RestockSubscription.Status.ACTIVE,
            expires_at__lte=now,
        ).update(status=RestockSubscription.Status.EXPIRED, updated_at=now)
        subscription, created = self.get_or_create(
            **target_filter,
            phone_hash=keyed_digest(phone),
            status=RestockSubscription.Status.ACTIVE,
            defaults={
                'phone_number': phone,
                'customer': customer,
                'expires_at': now + timedelta(days=90),
            },
        )
        if not created and customer is not None and subscription.customer_id is None:
            subscription.customer = customer
            subscription.save(update_fields=['customer', 'updated_at'])
        return subscription


class RestockSubscription(models.Model):
    """One customer SMS request for one exact currently unavailable item."""

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Waiting'
        NOTIFIED = 'NOTIFIED', 'Notified'
        CANCELLED = 'CANCELLED', 'Cancelled'
        EXPIRED = 'EXPIRED', 'Expired'

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='restock_subscriptions',
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='restock_subscriptions',
        null=True,
        blank=True,
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='restock_subscriptions',
        null=True,
        blank=True,
    )
    phone_number = models.CharField(
        max_length=20,
        help_text='Normalized delivery number. Restricted customer contact data.',
    )
    phone_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True,
    )
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField(db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RestockSubscriptionManager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, variant__isnull=True)
                    | models.Q(product__isnull=True, variant__isnull=False)
                ),
                name='restock_subscription_exactly_one_target',
            ),
            models.UniqueConstraint(
                fields=['product', 'phone_hash'],
                condition=models.Q(status='ACTIVE', variant__isnull=True),
                name='unique_active_product_restock_phone',
            ),
            models.UniqueConstraint(
                fields=['variant', 'phone_hash'],
                condition=models.Q(status='ACTIVE', product__isnull=True),
                name='unique_active_variant_restock_phone',
            ),
        ]

    @property
    def catalog_product(self):
        return self.variant.product if self.variant_id else self.product

    @property
    def item_label(self):
        if self.variant_id:
            return f'{self.variant.product.name} ({self.variant.option_summary})'
        return self.product.name

    def clean(self):
        super().clean()
        if bool(self.product_id) == bool(self.variant_id):
            raise ValidationError('Choose exactly one product or variant.')

    def save(self, *args, **kwargs):
        from notifications.services import keyed_digest, normalize_phone

        self.phone_number = normalize_phone(self.phone_number)
        self.phone_hash = keyed_digest(self.phone_number)
        if self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(days=90)
        self.full_clean(exclude=['phone_hash'])
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.item_label} restock alert ({self.status})'
