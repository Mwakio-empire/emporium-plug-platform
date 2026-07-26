
import uuid
from django.db import models
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Clean production-grade safe SKU generation protocol
        if not self.sku:
            prefix = self.category.name[:3].upper() if self.category else "PRD"
            unique_suffix = str(uuid.uuid4()).split('-')[0].upper()
            self.sku = f"{prefix}-{unique_suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    """
    Sub-product variations tracking combinations like size, color, or custom fields.
    """
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name='variants'
    )
    attribute_name = models.CharField(max_length=50, help_text="e.g., Size, Color")
    attribute_value = models.CharField(max_length=50, help_text="e.g., Large, Crimson Red")
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
        unique_together = ('product', 'attribute_name', 'attribute_value')

    @property
    def effective_price(self):
        # Fall back to global base price context if an item variant doesn't require separate price rules
        return self.price_override if self.price_override is not None else self.product.price

    def __str__(self):
        return f"{self.product.name} ({self.attribute_name}: {self.attribute_value})"


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
