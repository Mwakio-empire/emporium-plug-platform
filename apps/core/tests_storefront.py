from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from catalog.models import Category, Product, ProductImage, ProductVariant
from inventory.models import Stock
from orders.models import Order, OrderItem


User = get_user_model()


class StorefrontCatalogTests(TestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(name='Storefront Branch A', location='Nakuru')
        self.branch_b = Branch.objects.create(name='Storefront Branch B', location='Nairobi')
        self.parent = Category.objects.create(name='Storefront Home', slug='storefront-home')
        self.child = Category.objects.create(
            name='Storefront Kitchen', slug='storefront-kitchen', parent=self.parent,
        )
        self.hidden_category = Category.objects.create(
            name='Storefront Hidden Category', slug='storefront-hidden-category', is_visible=False,
        )
        self.kettle = Product.objects.create(
            name='Reliable Kettle', slug='reliable-kettle', sku='STORE-KETTLE',
            description='Quick hot water', category=self.child,
            price=Decimal('1500.00'), status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch_a, product=self.kettle, quantity=4)
        self.radio = Product.objects.create(
            name='Portable Radio', slug='portable-radio', sku='STORE-RADIO',
            category=self.child, price=Decimal('2500.00'), status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch_b, product=self.radio, quantity=3)
        self.hidden_product = Product.objects.create(
            name='Hidden Product', slug='hidden-product-storefront',
            category=self.child, price=Decimal('100.00'), status=Product.Status.HIDDEN,
        )
        self.in_invisible_category = Product.objects.create(
            name='Invisible Category Product', slug='invisible-category-product',
            category=self.hidden_category, price=Decimal('200.00'), status=Product.Status.ACTIVE,
        )
        self.sales_actor = User.objects.create_user(
            username='storefront_sales_actor', phone_number='+254700880001',
            email='storefront-sales@example.test', password='StrongPass123!',
            role=User.Role.CUSTOMER,
        )

    def _record_sale(
        self, product, *, quantity, status,
        order_type=Order.OrderType.WALK_IN, days_ago=0,
    ):
        order = Order.objects.create(
            branch=self.branch_a,
            order_type=order_type,
            customer=self.sales_actor,
            customer_phone=self.sales_actor.phone_number,
            payment_method=Order.PaymentMethod.COD,
            processed_by=self.sales_actor,
            status=status,
            subtotal=product.price * quantity,
            total_payable=product.price * quantity,
        )
        OrderItem.objects.create(
            order=order, product=product, quantity=quantity,
            unit_price=product.price, total_price=product.price * quantity,
        )
        if days_ago:
            Order.objects.filter(pk=order.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago),
            )
        return order

    def test_public_listing_excludes_hidden_product_and_invisible_category(self):
        response = self.client.get(reverse('core:catalog_filter_engine'))
        self.assertContains(response, self.kettle.name)
        self.assertNotContains(response, self.hidden_product.name)
        self.assertNotContains(response, self.in_invisible_category.name)

    def test_simple_in_stock_product_has_add_to_cart_action(self):
        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'search': 'Reliable Kettle', 'branch': self.branch_a.pk,
        })
        self.assertContains(response, 'Add to cart')
        self.assertContains(response, f'name="product_id" value="{self.kettle.pk}"')

    def test_branch_and_search_filters_are_combined(self):
        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'branch': self.branch_a.pk,
            'availability': 'in_stock',
            'search': 'Kettle',
        })
        self.assertContains(response, self.kettle.name)
        self.assertNotContains(response, self.radio.name)

    def test_parent_category_filter_includes_visible_descendants(self):
        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'category': self.parent.pk,
        })
        self.assertContains(response, self.kettle.name)
        self.assertContains(response, self.radio.name)

    def test_price_sort_is_applied(self):
        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'sort': 'price_desc',
        })
        products = list(response.context['products'])
        self.assertEqual(products[:2], [self.radio, self.kettle])

    def test_best_selling_counts_only_recent_fulfilled_quantities(self):
        self._record_sale(
            self.kettle, quantity=100, status=Order.Status.COMPLETED, days_ago=91,
        )
        self._record_sale(self.kettle, quantity=50, status=Order.Status.PENDING)
        self._record_sale(
            self.kettle, quantity=2, status=Order.Status.DELIVERED,
            order_type=Order.OrderType.ONLINE_DELIVERY,
        )
        self._record_sale(
            self.radio, quantity=3, status=Order.Status.COLLECTED,
            order_type=Order.OrderType.ONLINE_PICKUP,
        )
        self._record_sale(
            self.radio, quantity=40, status=Order.Status.CANCELLED,
            order_type=Order.OrderType.ONLINE_DELIVERY,
        )

        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'sort': 'best_selling',
        })
        products = list(response.context['products'])
        self.assertEqual(products[:2], [self.radio, self.kettle])
        self.assertEqual(products[0].sales_quantity, 3)
        self.assertEqual(products[1].sales_quantity, 2)

    def test_invalid_filter_values_do_not_crash(self):
        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'branch': 'not-a-branch', 'category': 'bad',
            'min_price': 'invalid', 'max_price': '-10', 'sort': 'unknown',
        })
        self.assertEqual(response.status_code, 200)

    def test_product_detail_hides_product_in_invisible_category(self):
        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': self.in_invisible_category.slug},
        ))
        self.assertEqual(response.status_code, 404)

    def test_product_detail_uses_company_wide_stock_without_branch_selector(self):
        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': self.kettle.slug},
        ))
        self.assertContains(response, 'Low stock - order soon')
        self.assertNotContains(response, 'Choose a branch')
        self.assertNotContains(response, 'detail-branch')

    def test_product_card_adds_without_customer_branch_selection(self):
        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'search': self.kettle.name,
        })
        self.assertContains(response, 'Add to cart')
        self.assertNotContains(response, 'Choose a branch')

    def test_variant_product_requires_option_selection(self):
        shirt = Product.objects.create(
            name='Choice Shirt', slug='choice-shirt', category=self.child,
            price=Decimal('900.00'), status=Product.Status.ACTIVE,
        )
        variant = ProductVariant.objects.create(
            product=shirt, attribute_name='Size', attribute_value='Medium',
        )
        Stock.objects.create(branch=self.branch_a, variant=variant, quantity=2)
        response = self.client.get(reverse('core:catalog_filter_engine'), {
            'search': 'Choice Shirt', 'branch': self.branch_a.pk,
        })
        self.assertContains(response, 'Choose options')
        self.assertNotContains(response, 'Add to cart')

    def test_home_uses_customer_facing_copy_and_exposes_filters(self):
        response = self.client.get(reverse('core:storefront_home'))
        self.assertContains(response, 'Quality finds. Fair value. Shop with confidence.')
        self.assertContains(response, 'Filter &amp; sort')
        self.assertNotContains(response, 'Branch availability')
        self.assertNotContains(response, 'Continuous Evolution Layer')
        self.assertNotContains(response, 'Collection Matrix')
        self.assertContains(response, self.kettle.name)
        self.assertContains(response, 'aria-hidden="true" inert')
        self.assertContains(response, 'Skip to main content')
        self.assertContains(response, '/static/core/storefront.js')
        self.assertContains(response, '/static/core/storefront.css')
        self.assertContains(response, '/static/vendor/htmx.min.js')
        self.assertNotContains(response, 'cdn.tailwindcss.com')
        self.assertNotContains(response, 'unpkg.com/htmx')
        self.assertNotContains(response, 'onclick=')
        self.assertContains(response, 'aria-label="Shop categories"')
        self.assertContains(response, 'hx-target="#product-grid-target"')
        self.assertContains(response, self.parent.name)
        self.assertContains(response, self.child.name)

    def test_visible_child_of_hidden_parent_is_not_public(self):
        hidden_parent = Category.objects.create(
            name='Hidden Parent', slug='hidden-parent', is_visible=False,
        )
        visible_child = Category.objects.create(
            name='Visible Child', slug='visible-child', parent=hidden_parent,
            is_visible=True,
        )
        hidden_product = Product.objects.create(
            name='Ancestor Hidden Product', slug='ancestor-hidden-product',
            category=visible_child, price=Decimal('250.00'),
            status=Product.Status.ACTIVE,
        )
        response = self.client.get(reverse('core:storefront_home'))
        self.assertNotContains(response, hidden_product.name)
        self.assertNotContains(response, visible_child.name)

    def test_full_page_filters_work_without_htmx(self):
        response = self.client.get(reverse('core:storefront_home'), {
            'search': self.kettle.name,
            'availability': 'in_stock',
        })
        self.assertContains(response, self.kettle.name)
        self.assertNotContains(response, self.radio.name)
        self.assertNotContains(response, 'name="branch"')

    def test_html_catalog_is_paginated_without_hiding_later_products(self):
        for index in range(25):
            Product.objects.create(
                name=f'Paged Product {index:02d}',
                slug=f'paged-product-{index:02d}',
                category=self.child,
                price=Decimal('500.00') + index,
                status=Product.Status.ACTIVE,
            )
        first = self.client.get(reverse('core:catalog_filter_engine'))
        second = self.client.get(reverse('core:catalog_filter_engine'), {'page': 2})
        self.assertEqual(len(first.context['products']), 24)
        self.assertGreater(len(second.context['products']), 0)
        self.assertContains(first, 'Page 1 of 2')
        self.assertContains(second, 'Page 2 of 2')

    def test_product_detail_renders_gallery_specifications_and_seo(self):
        self.kettle.meta_description = 'A dependable kettle for everyday use.'
        self.kettle.specifications = {'Capacity': '1.7 litres', 'Warranty': '12 months'}
        self.kettle.save(update_fields=['meta_description', 'specifications'])
        ProductImage.objects.create(
            product=self.kettle,
            image='catalog_products/gallery/kettle-side.jpg',
            alt_text='Reliable kettle viewed from the side',
            sort_order=1,
        )
        response = self.client.get(
            reverse('core:product_detail', kwargs={'slug': self.kettle.slug}),
            {'branch': self.branch_a.pk},
        )
        self.assertContains(response, self.kettle.meta_description)
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'application/ld+json')
        self.assertContains(response, 'Emporium Plug')
        self.assertContains(response, 'NewCondition')
        self.assertContains(response, 'Reliable kettle viewed from the side')
        self.assertContains(response, 'Capacity')
        self.assertContains(response, '1.7 litres')
        self.assertContains(response, 'name="quantity"')
        self.assertNotContains(response, 'max="4"')
        self.assertContains(response, 'Low stock - order soon')
        self.assertContains(response, '/static/core/product_detail.js')
        self.assertNotContains(response, 'onclick=')

    def test_sitemap_contains_only_public_products(self):
        response = self.client.get(reverse('core:sitemap'))
        self.assertEqual(response['Content-Type'], 'application/xml')
        self.assertContains(response, self.kettle.slug)
        self.assertContains(response, f'/category/{self.child.slug}/')
        self.assertContains(response, '/about/')
        self.assertNotContains(response, self.hidden_product.slug)
        self.assertNotContains(response, self.in_invisible_category.slug)

    def test_robots_policy_links_to_sitemap_and_blocks_internal_areas(self):
        response = self.client.get(reverse('core:robots'))
        self.assertContains(response, 'Sitemap: http://testserver/sitemap.xml')
        self.assertContains(response, 'Disallow: /admin/')
        self.assertContains(response, 'Disallow: /management/')
        self.assertContains(response, 'User-agent: OAI-SearchBot')

    def test_category_page_has_unique_metadata_and_filtered_products(self):
        response = self.client.get(reverse(
            'core:category_storefront', kwargs={'slug': self.child.slug},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'Shop {self.child.name}')
        self.assertContains(response, f'/category/{self.child.slug}/')
        self.assertContains(response, self.kettle.name)
