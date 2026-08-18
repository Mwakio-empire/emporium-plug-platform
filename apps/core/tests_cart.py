# apps/core/tests_cart.py
#
# Django's built-in test runner (TestCase + test Client, unittest-style).
# Placed as a separate file matching the tests_pos.py precedent already
# established in this project, rather than bloating core/tests.py.
#
# These are plain Django views (not DRF), so we use django.test.Client
# with content_type='application/json', not rest_framework's APIClient.
#
# Every test here targets a SPECIFIC bug or fix traced this session:
#   - the has_variants FieldError -> product.variants.exists() fix
#   - the is_active FieldError removal on ProductVariant
#   - Sum() aggregation replacing Python sum()
#   - stale cart entry self-healing
#   - quantity > 0 validation on Add (but NOT Update, where <=0 = remove)
#   - JSONDecodeError handling via the _parse_json_body helper
#   - session isolation between customers
#
# Uniqueness discipline: every Branch/Category/Product/ProductVariant
# created uses a distinct name/slug per test via setUp(), so an unrelated
# uniqueness constraint never masks the actual behaviour under test.

import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock
from orders.cart_services import STOREFRONT_SELECTED_BRANCH_KEY
from orders.models import CustomerCart

User = get_user_model()


class CartTestDataMixin:
    """
    Builds a small, internally-consistent catalog + stock for cart tests:
      - "Cart Test Kettle": simple product, in stock (10 units, one branch)
      - "Cart Test Radio": simple product, OUT of stock (no Stock row)
      - "Cart Test Shirt": product WITH a variant (must be rejected by
        add_product() and only accepted by add_variant())
      - variant of the shirt: in stock (5 units)
      - "Cart Test Multi Branch Mug": simple product with stock split
        across TWO branches, to verify Sum() aggregation sums correctly
    """

    def setUp(self):
        self.branch_a = Branch.objects.create(name="Cart Test Branch A", location="A")
        self.branch_b = Branch.objects.create(name="Cart Test Branch B", location="B")

        self.category = Category.objects.create(
            name="Cart Test Category", slug="cart-test-category",
        )

        self.product_kettle = Product.objects.create(
            name="Cart Test Kettle", slug="cart-test-kettle",
            category=self.category, price=Decimal("1000.00"),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch_a, product=self.product_kettle, quantity=10)

        self.product_radio = Product.objects.create(
            name="Cart Test Radio", slug="cart-test-radio",
            category=self.category, price=Decimal("2000.00"),
            status=Product.Status.ACTIVE,
        )
        # Deliberately no Stock row -- always out of stock

        self.product_shirt = Product.objects.create(
            name="Cart Test Shirt", slug="cart-test-shirt",
            category=self.category, price=Decimal("500.00"),
            status=Product.Status.ACTIVE,
        )
        self.variant_shirt = ProductVariant.objects.create(
            product=self.product_shirt,
            attribute_name="Size", attribute_value="Medium",
        )
        Stock.objects.create(branch=self.branch_a, variant=self.variant_shirt, quantity=5)

        self.product_mug = Product.objects.create(
            name="Cart Test Multi Branch Mug", slug="cart-test-mug",
            category=self.category, price=Decimal("300.00"),
            status=Product.Status.ACTIVE,
        )
        # Stock split across two branches -- tests Sum() aggregation sums
        # across ALL branches, not just one
        Stock.objects.create(branch=self.branch_a, product=self.product_mug, quantity=3)
        Stock.objects.create(branch=self.branch_b, product=self.product_mug, quantity=4)
        session = self.client.session
        session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch_a.pk
        session.save()

    def _post_json(self, url, data):
        return self.client.post(url, data=json.dumps(data), content_type='application/json')


class CartDetailViewTests(CartTestDataMixin, TestCase):

    def test_empty_cart_returns_zero_values(self):
        """
        WHAT: GET /cart/ with nothing added yet
        EXPECT: is_empty True, item_count 0, total '0'
        """
        url = reverse('cart:detail')
        response = self.client.get(url)
        data = response.json()

        self.assertTrue(data['is_empty'])
        self.assertEqual(data['item_count'], 0)
        self.assertEqual(data['total'], '0')


class AddToCartTests(CartTestDataMixin, TestCase):

    def test_add_automatically_assigns_fulfilling_branch(self):
        session = self.client.session
        session.pop(STOREFRONT_SELECTED_BRANCH_KEY, None)
        session.save()
        response = self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 1,
        })
        self.assertTrue(response.json()['success'])
        detail = self.client.get(reverse('cart:detail')).json()
        self.assertEqual(detail['branch_id'], self.branch_a.pk)

    def test_add_simple_product_success(self):
        """
        WHAT: POST /cart/add/ for a simple in-stock product
        EXPECT: success True, item_count reflects the addition
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 2,
        })
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['item_count'], 2)

    def test_add_out_of_stock_product_rejected(self):
        """
        WHAT: POST /cart/add/ for a product with zero Stock rows
        EXPECT: success False, error mentions out of stock
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'product', 'id': str(self.product_radio.id), 'quantity': 1,
        })
        data = response.json()

        self.assertFalse(data['success'])
        self.assertIn('out of stock', data['error'])

    def test_add_product_with_variants_rejected(self):
        """
        WHAT: POST /cart/add/ type=product for a product that HAS a variant
        EXPECT: success False, error about needing to select an option

        This is the direct regression test for the bug fixed this session:
        add_product() used to crash with FieldError querying a nonexistent
        has_variants field. It now correctly uses product.variants.exists()
        and rejects simple-add for variant products with a clean error
        instead of crashing.
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'product', 'id': str(self.product_shirt.id), 'quantity': 1,
        })
        data = response.json()

        self.assertEqual(response.status_code, 200)  # no crash -- this is the point
        self.assertFalse(data['success'])
        self.assertIn('options', data['error'])

    def test_add_variant_success(self):
        """
        WHAT: POST /cart/add/ type=variant for the shirt's variant
        EXPECT: success True

        Regression test for the second fix: ProductVariant.objects.get()
        used to crash with FieldError filtering on a nonexistent
        is_active field. That filter was removed.
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'variant', 'id': str(self.variant_shirt.id), 'quantity': 1,
        })
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])

    def test_add_zero_quantity_rejected(self):
        """
        WHAT: POST /cart/add/ with quantity=0
        EXPECT: 400 -- Add view requires quantity > 0 (suggestion #1)
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 0,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('at least one', response.json()['error'])

    def test_add_negative_quantity_rejected(self):
        """
        WHAT: POST /cart/add/ with quantity=-3
        EXPECT: 400 -- same positive-only rule as the zero case
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': -3,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('at least one', response.json()['error'])

    def test_add_non_numeric_quantity_rejected(self):
        """
        WHAT: POST /cart/add/ with quantity='abc'
        EXPECT: 400, clean error -- not an unhandled 500
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 'abc',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('whole number', response.json()['error'])

    def test_add_invalid_json_body_rejected(self):
        """
        WHAT: POST /cart/add/ with a malformed JSON body
        EXPECT: 400 -- tests the _parse_json_body helper and
                json.JSONDecodeError handling specifically
        """
        url = reverse('cart:add')
        response = self.client.post(
            url, data='{not valid json', content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Refresh the page', response.json()['error'])

    def test_add_missing_fields_rejected(self):
        """
        WHAT: POST /cart/add/ with no type or id
        EXPECT: 400
        """
        url = reverse('cart:add')
        response = self._post_json(url, {'quantity': 1})

        self.assertEqual(response.status_code, 400)

    def test_add_unknown_type_rejected(self):
        """
        WHAT: POST /cart/add/ with type='bogus'
        EXPECT: 400
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'bogus', 'id': str(self.product_kettle.id), 'quantity': 1,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('identify that product', response.json()['error'])

    def test_add_quantity_exceeding_stock_gets_capped_with_warning(self):
        """
        WHAT: POST /cart/add/ requesting more units than exist
        EXPECT: success True, warning present, quantity actually capped
                at available stock (verified via a follow-up GET /cart/)
        """
        add_url = reverse('cart:add')
        response = self._post_json(add_url, {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 999,
        })
        data = response.json()

        self.assertTrue(data['success'])
        self.assertIn('warning', data)
        self.assertEqual(
            data['warning'],
            'Quantity reduced to what is currently available.',
        )

        detail_response = self.client.get(reverse('cart:detail'))
        detail_data = detail_response.json()
        kettle_item = next(
            i for i in detail_data['items'] if i['product_id'] == str(self.product_kettle.id)
        )
        self.assertEqual(kettle_item['quantity'], 10)  # capped at actual stock, not 999

    def test_cart_caps_stock_to_selected_branch(self):
        """
        WHAT: A product has Stock rows in TWO branches (3 + 4 = 7 total)
        EXPECT: The cart uses only the selected branch's 3 units and
                never promises inventory held by the other branch.
        """
        url = reverse('cart:add')
        response = self._post_json(url, {
            'type': 'product', 'id': str(self.product_mug.id), 'quantity': 3,
        })
        data = response.json()
        self.assertTrue(data['success'])
        self.assertNotIn('warning', data)

        # Reset and request the quantity held by branch B. The cart may move
        # internally, but must not sum the 3 + 4 units into seven available.
        session = self.client.session
        session.clear()
        session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch_a.pk
        session.save()
        response2 = self._post_json(url, {
            'type': 'product', 'id': str(self.product_mug.id), 'quantity': 4,
        })
        data2 = response2.json()
        self.assertTrue(data2['success'])
        self.assertNotIn('warning', data2)
        self.assertEqual(self.client.get(reverse('cart:detail')).json()['branch_id'], self.branch_b.pk)

    def test_cart_rejects_items_no_single_branch_can_fulfil(self):
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 1,
        })
        branch_b_only = Product.objects.create(
            name='Branch B Only Item', slug='branch-b-only-item',
            category=self.category, price=Decimal('400.00'),
            status=Product.Status.ACTIVE,
        )
        Stock.objects.create(branch=self.branch_b, product=branch_b_only, quantity=2)
        response = self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(branch_b_only.id), 'quantity': 1,
        })
        self.assertFalse(response.json()['success'])
        self.assertIn('not currently available together', response.json()['error'])

    def test_cart_detail_exposes_fulfilling_branch(self):
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 1,
        })
        detail = self.client.get(reverse('cart:detail')).json()
        self.assertEqual(detail['branch_id'], self.branch_a.pk)
        self.assertEqual(detail['branch_name'], self.branch_a.name)

    def test_html_cart_gateway_honors_requested_quantity(self):
        response = self.client.post(reverse('core:cart_action_gateway'), {
            'action': 'add', 'product_id': self.product_kettle.pk, 'quantity': 3,
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        detail = self.client.get(reverse('cart:detail')).json()
        self.assertEqual(detail['item_count'], 3)

    def test_html_cart_gateway_redirects_without_htmx(self):
        response = self.client.post(
            reverse('core:cart_action_gateway'),
            {'action': 'add', 'product_id': self.product_kettle.pk, 'quantity': 2},
            HTTP_REFERER=reverse('core:storefront_home'),
        )
        self.assertRedirects(response, reverse('core:storefront_home'))
        self.assertEqual(self.client.get(reverse('cart:detail')).json()['item_count'], 2)


class UpdateCartTests(CartTestDataMixin, TestCase):

    def test_update_to_zero_removes_item(self):
        """
        WHAT: POST /cart/update/ with quantity=0 on an existing item
        EXPECT: item removed -- this is INTENTIONAL behaviour, unlike
                the Add view which rejects zero. Confirms the two views
                correctly implement different rules for the same value.
        """
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 3,
        })
        key = f"p:{self.product_kettle.id}"

        response = self._post_json(reverse('cart:update'), {'key': key, 'quantity': 0})
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['item_count'], 0)

    def test_update_negative_quantity_removes_item(self):
        """
        WHAT: POST /cart/update/ with quantity=-1
        EXPECT: same removal behaviour as zero
        """
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 3,
        })
        key = f"p:{self.product_kettle.id}"

        response = self._post_json(reverse('cart:update'), {'key': key, 'quantity': -1})
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['item_count'], 0)

    def test_update_nonexistent_key_returns_failure(self):
        """
        WHAT: POST /cart/update/ for a key never added to the cart
        EXPECT: success False, clean error -- not a crash
        """
        response = self._post_json(reverse('cart:update'), {
            'key': 'p:00000000-0000-0000-0000-000000000000', 'quantity': 2,
        })
        data = response.json()

        self.assertFalse(data['success'])
        self.assertIn('not in cart', data['error'])


class RemoveFromCartTests(CartTestDataMixin, TestCase):

    def test_remove_existing_item_succeeds(self):
        """
        WHAT: POST /cart/remove/ for an item actually in the cart
        EXPECT: success True, item_count drops to 0
        """
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 1,
        })
        key = f"p:{self.product_kettle.id}"

        response = self._post_json(reverse('cart:remove'), {'key': key})
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['item_count'], 0)

    def test_remove_nonexistent_item_returns_false(self):
        """
        WHAT: POST /cart/remove/ for a key never added
        EXPECT: success False -- not an error, just nothing to remove
        """
        response = self._post_json(reverse('cart:remove'), {
            'key': 'p:00000000-0000-0000-0000-000000000000',
        })
        data = response.json()

        self.assertFalse(data['success'])


class StaleEntrySelfHealTests(CartTestDataMixin, TestCase):

    def test_deleted_product_removed_from_cart_automatically(self):
        """
        WHAT: Add a product to the cart, then DELETE that product from
              the database entirely, then GET /cart/
        EXPECT: The stale entry is silently dropped from the session
                (not just skipped in the response) -- this is the
                self-healing fix (suggestion #2). Confirmed by checking
                the item no longer appears AND a second GET still shows
                it gone (proving it was actually removed from the
                session, not just filtered out that one time).
        """
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': str(self.product_kettle.id),
            'quantity': 1,
        })

        # Delete the product entirely -- simulates a product being
        # removed from the catalog while sitting in someone's cart
        self.product_kettle.delete()

        first_response = self.client.get(reverse('cart:detail'))
        first_data = first_response.json()
        self.assertEqual(len(first_data['items']), 0)
        self.assertTrue(first_data['is_empty'])

        # Second GET confirms it was actually removed from the session,
        # not just filtered out of that one response
        second_response = self.client.get(reverse('cart:detail'))
        second_data = second_response.json()
        self.assertEqual(len(second_data['items']), 0)


class SessionIsolationTests(CartTestDataMixin, TestCase):

    def test_two_customers_have_independent_carts(self):
        """
        WHAT: Two separate Client instances (simulating two different
              customers/browsers) each add different items
        EXPECT: Neither client sees the other's cart contents --
                confirms UnifiedSessionCartService is correctly scoped
                to request.session per visitor
        """
        client_1 = Client()
        client_2 = Client()
        session_1 = client_1.session
        session_1[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch_a.pk
        session_1.save()
        session_2 = client_2.session
        session_2[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch_b.pk
        session_2.save()

        client_1.post(
            reverse('cart:add'),
            data=json.dumps({
                'type': 'product', 'id': str(self.product_kettle.id), 'quantity': 1,
            }),
            content_type='application/json',
        )
        client_2.post(
            reverse('cart:add'),
            data=json.dumps({
                'type': 'product', 'id': str(self.product_mug.id), 'quantity': 1,
            }),
            content_type='application/json',
        )

        cart_1 = client_1.get(reverse('cart:detail')).json()
        cart_2 = client_2.get(reverse('cart:detail')).json()

        self.assertEqual(cart_1['item_count'], 1)
        self.assertEqual(cart_2['item_count'], 1)

        cart_1_product_ids = [i['product_id'] for i in cart_1['items']]
        cart_2_product_ids = [i['product_id'] for i in cart_2['items']]

        self.assertIn(str(self.product_kettle.id), cart_1_product_ids)
        self.assertNotIn(str(self.product_mug.id), cart_1_product_ids)
        self.assertIn(str(self.product_mug.id), cart_2_product_ids)
        self.assertNotIn(str(self.product_kettle.id), cart_2_product_ids)


class AuthenticatedCartPersistenceTests(CartTestDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.customer = User.objects.create_user(
            username='savedcartcustomer',
            phone_number='+254711880001',
            email='savedcartcustomer@test.com',
            password='SavedCartPass123!',
        )

    def test_authenticated_cart_is_saved_and_restored_in_new_session(self):
        self.client.force_login(self.customer)
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': self.product_kettle.pk, 'quantity': 2,
        })
        saved = CustomerCart.objects.get(
            customer=self.customer, branch=self.branch_a,
        )
        self.assertEqual(saved.data[f'p:{self.product_kettle.pk}']['quantity'], 2)

        other_client = Client()
        other_client.force_login(self.customer)
        session = other_client.session
        session[STOREFRONT_SELECTED_BRANCH_KEY] = self.branch_a.pk
        session.save()
        restored = other_client.get(reverse('cart:detail')).json()
        self.assertEqual(restored['item_count'], 2)
        self.assertEqual(restored['branch_id'], self.branch_a.pk)

    def test_customer_login_merges_guest_and_saved_cart_for_same_branch(self):
        CustomerCart.objects.create(
            customer=self.customer,
            branch=self.branch_a,
            data={
                f'p:{self.product_kettle.pk}': {
                    'type': 'product',
                    'product_id': str(self.product_kettle.pk),
                    'quantity': 1,
                    'price': str(self.product_kettle.price),
                    'name': self.product_kettle.name,
                    'sku': self.product_kettle.sku,
                },
            },
        )
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': self.product_kettle.pk, 'quantity': 2,
        })
        response = self.client.post(reverse('accounts:login'), {
            'identifier': self.customer.username,
            'password': 'SavedCartPass123!',
        })
        self.assertEqual(response.status_code, 302)
        merged = self.client.get(reverse('cart:detail')).json()
        self.assertEqual(merged['item_count'], 3)
        self.assertEqual(
            CustomerCart.objects.get(customer=self.customer, branch=self.branch_a)
            .data[f'p:{self.product_kettle.pk}']['quantity'],
            3,
        )

    def test_emptying_cart_removes_saved_cart_for_that_branch(self):
        self.client.force_login(self.customer)
        self._post_json(reverse('cart:add'), {
            'type': 'product', 'id': self.product_kettle.pk, 'quantity': 1,
        })
        self._post_json(reverse('cart:remove'), {'key': f'p:{self.product_kettle.pk}'})
        self.assertFalse(CustomerCart.objects.filter(
            customer=self.customer, branch=self.branch_a,
        ).exists())
