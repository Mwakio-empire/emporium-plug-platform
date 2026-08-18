# apps/catalog/tests/test_catalog_api.py
#
# Uses Django's built-in test runner via APITestCase (unittest-style,
# compatible with `python manage.py test`).
#
# Field references traced to verified source:
#   Category: name(unique), slug, parent(related_name='subcategories'), is_visible
#     -- apps/catalog/models.py
#   Product: name, slug(unique), sku(auto-gen), category(FK), price,
#     compare_at_price, status(ACTIVE/HIDDEN/OUT_OF_STOCK -- uppercase)
#     -- apps/catalog/models.py
#   ProductVariant: product(FK, related_name='variants'), attribute_name,
#     attribute_value, price_override, effective_price property
#     -- apps/catalog/models.py
#   Branch: name(unique), location, is_active -- apps/branches/models.py
#   Stock: variant(FK nullable), product(FK nullable), branch(FK), quantity
#     -- apps/inventory/models.py
#
# Uniqueness discipline: every Category.name / Category.slug / Product.slug
# created in a test is distinct from every other test AND every other
# object within the same test. Django TestCase wraps each test method in
# its own transaction and rolls back after, so cross-test collisions are
# not possible -- but within-test collisions (e.g. two products both named
# "Test Product") are avoided explicitly so a uniqueness IntegrityError
# never masks the behaviour actually being tested.

from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse

from catalog.models import Category, Product, ProductImage, ProductVariant
from branches.models import Branch
from inventory.models import Stock


class CatalogTestDataMixin:
    """
    Shared setup building a small, internally-consistent catalog:
      Electronics (category)
        -> Phones (subcategory)
      Products:
        - "Simple Kettle" (no variants, in stock, not on sale)
        - "Discounted Blender" (no variants, in stock, on sale)
        - "Variant Shirt" (has variants, in stock via variant stock)
        - "Hidden Mug" (status=HIDDEN -- must never appear in public listing)
        - "Out of Stock Radio" (status=ACTIVE, zero stock everywhere)
    """

    def setUp(self):
        self.branch = Branch.objects.create(
            name="Catalog Test Branch",
            location="Test Location",
            is_active=True,
        )

        self.category_electronics = Category.objects.create(
            name="Electronics Catalog Test",
            slug="electronics-catalog-test",
            is_visible=True,
        )
        self.category_phones = Category.objects.create(
            name="Phones Catalog Test",
            slug="phones-catalog-test",
            parent=self.category_electronics,
            is_visible=True,
        )

        self.product_kettle = Product.objects.create(
            name="Simple Kettle",
            slug="simple-kettle-catalog-test",
            category=self.category_electronics,
            price=Decimal("1500.00"),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch, product=self.product_kettle, quantity=10)

        self.product_blender = Product.objects.create(
            name="Discounted Blender",
            slug="discounted-blender-catalog-test",
            category=self.category_electronics,
            price=Decimal("3000.00"),
            compare_at_price=Decimal("4000.00"),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch, product=self.product_blender, quantity=5)

        self.product_shirt = Product.objects.create(
            name="Variant Shirt",
            slug="variant-shirt-catalog-test",
            category=self.category_phones,
            price=Decimal("800.00"),
            status=Product.Status.ACTIVE,
        )
        self.variant_shirt_small = ProductVariant.objects.create(
            product=self.product_shirt,
            attribute_name="Size",
            attribute_value="Small",
        )
        Stock.objects.create(
            branch=self.branch, variant=self.variant_shirt_small, quantity=7,
        )

        self.product_hidden_mug = Product.objects.create(
            name="Hidden Mug",
            slug="hidden-mug-catalog-test",
            category=self.category_electronics,
            price=Decimal("500.00"),
            status=Product.Status.HIDDEN,
        )
        Stock.objects.create(branch=self.branch, product=self.product_hidden_mug, quantity=20)

        self.product_out_of_stock = Product.objects.create(
            name="Out of Stock Radio",
            slug="out-of-stock-radio-catalog-test",
            category=self.category_electronics,
            price=Decimal("2500.00"),
            status=Product.Status.ACTIVE,
        )
        # Deliberately no Stock row created -- zero stock everywhere


class CategoryTreeViewTests(CatalogTestDataMixin, APITestCase):

    def test_top_level_categories_returned(self):
        """
        WHAT: GET /api/catalog/categories/
        EXPECT: 200, top-level category present, subcategory nested inside it
        """
        url = reverse('catalog:category-tree')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [c['name'] for c in response.data]
        self.assertIn("Electronics Catalog Test", names)

    def test_subcategory_nested_under_parent(self):
        """
        WHAT: Category tree response
        EXPECT: 'Phones Catalog Test' appears inside 'children' of its parent
                (serializer uses obj.subcategories, matching the model's
                actual related_name -- not 'children')
        """
        url = reverse('catalog:category-tree')
        response = self.client.get(url)

        parent = next(
            c for c in response.data if c['name'] == "Electronics Catalog Test"
        )
        child_names = [c['name'] for c in parent['children']]
        self.assertIn("Phones Catalog Test", child_names)

    def test_invisible_category_excluded(self):
        """
        WHAT: A category with is_visible=False exists
        EXPECT: It does not appear in the tree response
        """
        Category.objects.create(
            name="Invisible Category Test",
            slug="invisible-category-test",
            is_visible=False,
        )
        url = reverse('catalog:category-tree')
        response = self.client.get(url)

        names = [c['name'] for c in response.data]
        self.assertNotIn("Invisible Category Test", names)


class ProductListViewTests(CatalogTestDataMixin, APITestCase):

    def test_branch_filter_scopes_stock_without_exposing_exact_quantity(self):
        other_branch = Branch.objects.create(
            name='Other Catalog Branch', location='Other', is_active=True,
        )
        Stock.objects.create(
            branch=other_branch, product=self.product_out_of_stock, quantity=3,
        )
        url = reverse('catalog:product-list')
        response = self.client.get(url, {
            'branch': self.branch.pk,
            'in_stock': 'true',
        })
        products = {product['slug']: product for product in response.data['results']}
        self.assertIn(self.product_kettle.slug, products)
        self.assertEqual(products[self.product_kettle.slug]['stock_status'], 'IN_STOCK')
        self.assertNotIn('available_stock', products[self.product_kettle.slug])
        self.assertNotIn(self.product_out_of_stock.slug, products)

        other_response = self.client.get(url, {
            'branch': other_branch.pk,
            'in_stock': 'true',
        })
        other_slugs = [product['slug'] for product in other_response.data['results']]
        self.assertIn(self.product_out_of_stock.slug, other_slugs)
        self.assertNotIn(self.product_kettle.slug, other_slugs)

    def test_only_active_products_returned(self):
        """
        WHAT: GET /api/catalog/products/
        EXPECT: HIDDEN product excluded, ACTIVE products included
        """
        url = reverse('catalog:product-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn("simple-kettle-catalog-test", slugs)
        self.assertNotIn("hidden-mug-catalog-test", slugs)

    def test_filter_by_category_slug(self):
        """
        WHAT: GET ?category=phones-catalog-test
        EXPECT: Only products in that category returned
        """
        url = reverse('catalog:product-list') + "?category=phones-catalog-test"
        response = self.client.get(url)

        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn("variant-shirt-catalog-test", slugs)
        self.assertNotIn("simple-kettle-catalog-test", slugs)

    def test_filter_min_max_price(self):
        """
        WHAT: GET ?min_price=1000&max_price=2000
        EXPECT: Only the kettle (1500.00) falls in this range
        """
        url = reverse('catalog:product-list') + "?min_price=1000&max_price=2000"
        response = self.client.get(url)

        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn("simple-kettle-catalog-test", slugs)
        self.assertNotIn("discounted-blender-catalog-test", slugs)

    def test_filter_on_sale_true(self):
        """
        WHAT: GET ?on_sale=true
        EXPECT: Only the blender (compare_at_price > price) returned
        """
        url = reverse('catalog:product-list') + "?on_sale=true"
        response = self.client.get(url)

        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn("discounted-blender-catalog-test", slugs)
        self.assertNotIn("simple-kettle-catalog-test", slugs)

    def test_filter_in_stock_true_excludes_zero_stock(self):
        """
        WHAT: GET ?in_stock=true
        EXPECT: 'Out of Stock Radio' (no Stock row at all) is excluded,
                products with Stock quantity > 0 are included
        """
        url = reverse('catalog:product-list') + "?in_stock=true"
        response = self.client.get(url)

        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn("simple-kettle-catalog-test", slugs)
        self.assertNotIn("out-of-stock-radio-catalog-test", slugs)

    def test_search_by_name(self):
        """
        WHAT: GET ?search=Blender
        EXPECT: Only the blender matches
        """
        url = reverse('catalog:product-list') + "?search=Blender"
        response = self.client.get(url)

        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn("discounted-blender-catalog-test", slugs)
        self.assertEqual(len(slugs), 1)

    def test_ordering_by_price_ascending(self):
        """
        WHAT: GET ?ordering=price
        EXPECT: Results sorted lowest price first among visible ACTIVE products
        """
        url = reverse('catalog:product-list') + "?ordering=price"
        response = self.client.get(url)

        prices = [Decimal(p['price']) for p in response.data['results']]
        self.assertEqual(prices, sorted(prices))


class ProductDetailViewTests(CatalogTestDataMixin, APITestCase):

    def test_detail_includes_specifications_and_gallery(self):
        self.product_kettle.specifications = {'Capacity': '1.7 litres'}
        self.product_kettle.meta_description = 'A dependable kettle.'
        self.product_kettle.save(update_fields=['specifications', 'meta_description'])
        ProductImage.objects.create(
            product=self.product_kettle,
            image='catalog_products/gallery/api-kettle.jpg',
            alt_text='Kettle gallery image',
            sort_order=1,
        )
        response = self.client.get(reverse(
            'catalog:product-detail', kwargs={'slug': self.product_kettle.slug},
        ))
        self.assertEqual(response.data['specifications'], {'Capacity': '1.7 litres'})
        self.assertEqual(response.data['meta_description'], 'A dependable kettle.')
        self.assertEqual(response.data['gallery'][0]['alt_text'], 'Kettle gallery image')

    def test_detail_by_slug_returns_full_data(self):
        """
        WHAT: GET /api/catalog/products/simple-kettle-catalog-test/
        EXPECT: 200, correct name and category nested
        """
        url = reverse('catalog:product-detail', kwargs={'slug': 'simple-kettle-catalog-test'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], "Simple Kettle")
        self.assertEqual(response.data['category']['name'], "Electronics Catalog Test")
        self.assertEqual(response.data['stock_status'], 'IN_STOCK')
        self.assertNotIn('total_stock', response.data)

    def test_variant_product_includes_variants_list(self):
        """
        WHAT: GET detail for a product with a ProductVariant attached
        EXPECT: 'variants' list contains the variant with correct
                attribute_name/attribute_value (verified field names,
                not a generic 'name' field which does not exist on
                ProductVariant)
        """
        url = reverse('catalog:product-detail', kwargs={'slug': 'variant-shirt-catalog-test'})
        response = self.client.get(url)

        self.assertEqual(len(response.data['variants']), 1)
        variant_data = response.data['variants'][0]
        self.assertEqual(variant_data['attribute_name'], "Size")
        self.assertEqual(variant_data['attribute_value'], "Small")
        self.assertEqual(variant_data['stock_status'], 'IN_STOCK')
        self.assertNotIn('total_stock', variant_data)

    def test_hidden_product_returns_404_on_detail(self):
        """
        WHAT: GET detail for a HIDDEN status product
        EXPECT: 404 -- detail view queryset filters status=ACTIVE same as list view
        """
        url = reverse('catalog:product-detail', kwargs={'slug': 'hidden-mug-catalog-test'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_slug_returns_404(self):
        """
        WHAT: GET detail for a slug that was never created
        EXPECT: 404
        """
        url = reverse('catalog:product-detail', kwargs={'slug': 'this-slug-does-not-exist'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
