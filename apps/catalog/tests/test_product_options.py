from decimal import Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from inventory.models import Stock
from marketing.models import FlashSale

from catalog.models import (
    Category,
    Product,
    ProductOption,
    ProductOptionValue,
    ProductOptionValueImage,
)
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

    def test_colour_gallery_rejects_non_colour_option_values(self):
        image = ProductOptionValueImage(
            option_value=self.small,
            image='catalog_products/option_values/invalid',
            alt_text='Invalid size image',
        )

        with self.assertRaisesMessage(ValidationError, 'only be attached to colour options'):
            image.save()

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
        matrix = response.context['variant_matrix']
        self.assertTrue(all(item['available'] for item in matrix))
        self.assertTrue(all('stock' not in item for item in matrix))
        self.assertNotContains(response, '5 available')

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

    def test_colour_gallery_is_shared_across_sizes_and_exact_variant_image_wins(self):
        ProductOptionValueImage.objects.create(
            option_value=self.black,
            image='catalog_products/option_values/black-primary',
            alt_text='Black option hoodie front view',
            sort_order=0,
        )
        ProductOptionValueImage.objects.create(
            option_value=self.black,
            image='catalog_products/option_values/black-back',
            alt_text='Black option hoodie back view',
            sort_order=1,
        )
        self.product.image = 'catalog_products/option-values/product-fallback'
        self.product.save(update_fields=['image', 'updated_at'])
        variants = generate_missing_combinations(self.product.pk)
        branch = Branch.objects.create(name='Option Media S18', location='Nairobi')
        for variant in variants:
            Stock.objects.create(branch=branch, variant=variant, quantity=5)

        small_black = next(
            variant for variant in variants
            if set(variant.option_values.values_list('pk', flat=True)) == {
                self.small.pk, self.black.pk,
            }
        )
        medium_black = next(
            variant for variant in variants
            if set(variant.option_values.values_list('pk', flat=True)) == {
                self.medium.pk, self.black.pk,
            }
        )
        medium_orange = next(
            variant for variant in variants
            if set(variant.option_values.values_list('pk', flat=True)) == {
                self.medium.pk, self.orange.pk,
            }
        )
        small_black.image = 'catalog_products/variants/exact-small-black'
        small_black.save(update_fields=['image'])

        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': self.product.slug},
        ))

        matrix = {item['id']: item for item in response.context['variant_matrix']}
        self.assertIn('exact-small-black', matrix[small_black.pk]['media'][0]['url'])
        self.assertIn('black-primary', matrix[small_black.pk]['media'][1]['url'])
        self.assertIn('black-primary', matrix[medium_black.pk]['media'][0]['url'])
        self.assertIn('black-back', matrix[medium_black.pk]['media'][1]['url'])
        self.assertIn('product-fallback', matrix[medium_orange.pk]['media'][0]['url'])

        api_response = self.client.get(reverse(
            'catalog:product-detail', kwargs={'slug': self.product.slug},
        ))
        black_data = next(
            value
            for option in api_response.data['options'] if option['name'] == 'Colour'
            for value in option['values'] if value['value'] == 'Black'
        )
        self.assertEqual(len(black_data['images']), 2)
        self.assertEqual(black_data['images'][0]['alt_text'], 'Black option hoodie front view')
