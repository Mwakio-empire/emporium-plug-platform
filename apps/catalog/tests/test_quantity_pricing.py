from decimal import Decimal

from django.contrib.sessions.middleware import SessionMiddleware
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant, QuantityPriceTier
from catalog.pricing import QuantityPricingService
from inventory.models import Stock
from orders.cart_services import UnifiedSessionCartService


class QuantityPricingTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Bulk test', slug='bulk-test')
        self.product = Product.objects.create(
            name='Bulk shirt', slug='bulk-shirt', category=self.category,
            price=Decimal('1000.00'), minimum_order_quantity=1,
        )
        self.tier = QuantityPriceTier.objects.create(
            product=self.product, minimum_quantity=5,
            discount_percentage=Decimal('10.00'),
        )

    def test_highest_eligible_percentage_tier_is_applied(self):
        QuantityPriceTier.objects.create(
            product=self.product, minimum_quantity=10,
            discount_percentage=Decimal('15.00'),
        )
        quote = QuantityPricingService.quote(
            product=self.product,
            regular_unit_price=Decimal('1000.00'),
            current_unit_price=Decimal('1000.00'),
            product_quantity=12,
        )
        self.assertEqual(quote.unit_price, Decimal('850.00'))
        self.assertEqual(quote.tier_minimum, 10)
        self.assertTrue(quote.wholesale_applied)

    def test_lower_flash_sale_wins_without_stacking(self):
        quote = QuantityPricingService.quote(
            product=self.product,
            regular_unit_price=Decimal('1000.00'),
            current_unit_price=Decimal('800.00'),
            product_quantity=5,
        )
        self.assertEqual(quote.unit_price, Decimal('800.00'))
        self.assertEqual(quote.source, 'FLASH_SALE')
        self.assertFalse(quote.wholesale_applied)

    def test_database_rejects_duplicate_threshold(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            QuantityPriceTier.objects.create(
                product=self.product, minimum_quantity=5,
                discount_percentage=Decimal('20.00'),
            )

    def test_variants_of_same_product_count_together(self):
        branch = Branch.objects.create(name='Bulk branch', location='Nairobi')
        small = ProductVariant.objects.create(
            product=self.product, attribute_name='Size', attribute_value='Small',
        )
        large = ProductVariant.objects.create(
            product=self.product, attribute_name='Size', attribute_value='Large',
        )
        Stock.objects.create(branch=branch, variant=small, quantity=20)
        Stock.objects.create(branch=branch, variant=large, quantity=20)
        request = RequestFactory().get('/')
        SessionMiddleware(lambda response: response).process_request(request)
        request.session.save()
        cart = UnifiedSessionCartService(request)
        cart.add_variant(small.pk, quantity=2)
        cart.add_variant(large.pk, quantity=3)

        items = cart.get_cart_items_extended()

        self.assertEqual(len(items), 2)
        self.assertTrue(all(item['wholesale_applied'] for item in items))
        self.assertTrue(all(item['price'] == Decimal('900.00') for item in items))
        self.assertTrue(all(item['product_quantity'] == 5 for item in items))

    def test_minimum_order_is_reported_but_cart_can_be_built(self):
        self.product.minimum_order_quantity = 3
        self.product.save(update_fields=['minimum_order_quantity'])
        branch = Branch.objects.create(name='MOQ branch', location='Nairobi')
        Stock.objects.create(branch=branch, product=self.product, quantity=20)
        request = RequestFactory().get('/')
        SessionMiddleware(lambda response: response).process_request(request)
        request.session.save()
        cart = UnifiedSessionCartService(request)
        cart.add_product(self.product.pk, quantity=2)

        result = cart.revalidate_stock(branch=branch)

        self.assertFalse(result['valid'])
        self.assertEqual(result['minimum_order_issues'][0]['shortfall'], 1)
