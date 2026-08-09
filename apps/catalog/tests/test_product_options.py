from decimal import Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from inventory.models import Stock
from marketing.models import FlashSale

from catalog.models import Category, Product, ProductOption, ProductOptionValue
from catalog.variant_services import configure_variant, generate_missing_combinations


class ProductOptionCombinationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Option Test Fashion', slug='option-test-fashion')
        self.product = Product.objects.create(
            name='Option Test Hoodie', slug='option-test-hoodie', sku='OPTION-HOODIE',
            category=self.category, price=Decimal('2400.00'),
        )
        self.size = ProductOption.objects.create(product=self.product, name='Size', position=1)
        self.small = ProductOptionValue.objects.create(option=self.size, value='S', position=1)
        self.medium = ProductOptionValue.objects.create(option=self.size, value='M', position=2)
        self.colour = ProductOption.objects.create(
            product=self.product, name='Colour',
            display_type=ProductOption.DisplayType.COLOUR, position=2,
        )
        self.black = ProductOptionValue.objects.create(
            option=self.colour, value='Black', colour_hex='#111827', position=1,
        )
        self.orange = ProductOptionValue.objects.create(
            option=self.colour, value='Orange', colour_hex='#F97316', position=2,
        )

    def test_generator_creates_cartesian_combinations_once(self):
        created = generate_missing_combinations(self.product.pk)
        self.assertEqual(len(created), 4)
        self.assertEqual(generate_missing_combinations(self.product.pk), [])
        self.assertEqual(self.product.variants.count(), 4)
        for variant in self.product.variants.all():
            self.assertEqual(variant.option_values.count(), 2)
            self.assertTrue(variant.sku)
            self.assertTrue(variant.combination_signature)

    def test_configure_variant_rejects_incomplete_combination(self):
        variant = generate_missing_combinations(self.product.pk)[0]
        with self.assertRaisesMessage(ValidationError, 'every product option'):
            configure_variant(variant, [self.small])

    def test_colour_hex_validation_rejects_invalid_value(self):
        value = ProductOptionValue(option=self.colour, value='Invalid', colour_hex='orange')
        with self.assertRaises(ValidationError):
            value.full_clean()

    def test_storefront_renders_grouped_selectors_and_variant_matrix(self):
        variants = generate_missing_combinations(self.product.pk)
        branch = Branch.objects.create(name='Option Test S18', location='Nairobi')
        for variant in variants:
            Stock.objects.create(branch=branch, variant=variant, quantity=5)

        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': self.product.slug},
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-option-group', count=2)
        self.assertContains(response, 'variant-choice--text')
        self.assertContains(response, 'variant-choice--colour')
        self.assertContains(response, 'variant-colour-swatch')
        self.assertContains(response, f'data-colour-id="{self.black.pk}"')
        self.assertContains(response, 'fill="#111827"')
        self.assertContains(response, 'data-variant-message')
        self.assertContains(response, 'Colour')
        self.assertContains(response, 'Black')
        self.assertContains(response, 'variant-matrix-data')
        self.assertContains(response, variants[0].sku)

    def test_variant_matrix_includes_sale_and_regular_prices(self):
        variants = generate_missing_combinations(self.product.pk)
        selected_variant = variants[0]
        selected_variant.price_override = Decimal('2600.00')
        selected_variant.save(update_fields=['price_override'])
        branch = Branch.objects.create(name='Option Sale S18', location='Nairobi')
        for variant in variants:
            Stock.objects.create(branch=branch, variant=variant, quantity=5)
        FlashSale.objects.create(
            variant=selected_variant,
            sale_price=Decimal('2200.00'),
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': self.product.slug},
        ))

        sale_entry = next(
            item for item in response.context['variant_matrix']
            if item['id'] == selected_variant.pk
        )
        self.assertEqual(sale_entry['price'], '2200.00')
        self.assertEqual(sale_entry['regular_price'], '2600.00')
        self.assertIs(sale_entry['on_sale'], True)
        self.assertContains(response, 'id="variant-regular-price"')
