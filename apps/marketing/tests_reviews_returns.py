#apps/marketing/tests_reviews_returns.py
from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from orders.models import Order, OrderItem
from marketing.models import ProductReview, ReturnRequest
User = get_user_model()
class ReviewsReturnsTestDataMixin:
    def setUp(self):
        cache.clear()
        self.branch = Branch.objects.create(name="RR Test Branch", location="Test")
        self.other_branch = Branch.objects.create(name="RR Other Branch", location="Elsewhere")
        self.manager = User.objects.create_user(
            username='rrmanager0001', phone_number='+254799200001',
            email='rrmanager0001@test.com', password='ManagerPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.other_manager = User.objects.create_user(
            username='rrmanager0002', phone_number='+254799200002',
            email='rrmanager0002@test.com', password='ManagerPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.other_branch,
        )
        self.customer = User.objects.create_user(
            username='rrcustomer0001', phone_number='+254799200003',
            email='rrcustomer0001@test.com', password='CustPass123!',
            role=User.Role.CUSTOMER,
        )
        self.other_customer = User.objects.create_user(
            username='rrcustomer0002', phone_number='+254799200004',
            email='rrcustomer0002@test.com', password='CustPass123!',
            role=User.Role.CUSTOMER,
        )
        self.category = Category.objects.create(name="RR Category", slug="rr-category")
        self.product = Product.objects.create(
            name="RR Product", slug="rr-product",
            category=self.category, price=Decimal("1000.00"),
            status=Product.Status.ACTIVE,
            customer_return_policy=Product.CustomerReturnPolicy.SEVEN_DAY,
        )
        self.variant_product = Product.objects.create(
            name="RR Variant Product", slug="rr-variant-product",
            category=self.category, price=Decimal("500.00"),
            status=Product.Status.ACTIVE,
            customer_return_policy=Product.CustomerReturnPolicy.SEVEN_DAY,
        )
        self.variant = ProductVariant.objects.create(
            product=self.variant_product, attribute_name="Size", attribute_value="M",
        )
    def _make_order(self, *, customer, status_, branch=None, order_type=Order.OrderType.WALK_IN):
        return Order.objects.create(
            branch=branch or self.branch,
            customer=customer,
            order_type=order_type,
            customer_phone='+254700111111',
            payment_method=Order.PaymentMethod.CASH,
            status=status_,
            processed_by=customer,
            subtotal=Decimal('1000.00'),
            total_payable=Decimal('1000.00'),
        )
class ProductReviewViewTests(ReviewsReturnsTestDataMixin, APITestCase):
    def test_unauthenticated_cannot_post_review(self):
        response = self.client.post(reverse('marketing:reviews'), {
            'product_id': self.product.id, 'rating': 5, 'comment': 'Great',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    def test_no_purchase_rejected(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:reviews'), {
            'product_id': self.product.id, 'rating': 5, 'comment': 'Never bought this',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ProductReview.objects.filter(product=self.product, customer=self.customer).exists())
    def test_simple_product_purchase_allows_review(self):
        """Regression: original check only matched variant items, silently failing simple-product buyers."""
        order = self._make_order(customer=self.customer, status_=Order.Status.COMPLETED)
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'))
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:reviews'), {
            'product_id': self.product.id, 'rating': 4, 'comment': 'Solid item',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['is_verified_purchase'])
        self.assertFalse(response.data['is_approved'])
    def test_variant_product_delivered_status_allows_review(self):
        """Regression: online orders terminate at DELIVERED, never COMPLETED."""
        order = self._make_order(
            customer=self.customer, status_=Order.Status.DELIVERED,
            order_type=Order.OrderType.ONLINE_DELIVERY,
        )
        OrderItem.objects.create(order=order, variant=self.variant, quantity=1, unit_price=Decimal('500.00'))
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:reviews'), {
            'product_id': self.variant_product.id, 'rating': 5, 'comment': 'Fast delivery',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    def test_pending_order_does_not_count_as_purchase(self):
        order = self._make_order(customer=self.customer, status_=Order.Status.PENDING)
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'))
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:reviews'), {
            'product_id': self.product.id, 'rating': 3, 'comment': 'Not yet delivered',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    def test_duplicate_review_rejected(self):
        order = self._make_order(customer=self.customer, status_=Order.Status.COMPLETED)
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'))
        self.client.force_authenticate(user=self.customer)
        url = reverse('marketing:reviews')
        first = self.client.post(url, {'product_id': self.product.id, 'rating': 5, 'comment': 'First'}, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(url, {'product_id': self.product.id, 'rating': 1, 'comment': 'Second'}, format='json')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
    def test_unapproved_review_excluded_from_public_list(self):
        order = self._make_order(customer=self.customer, status_=Order.Status.COMPLETED)
        OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'))
        self.client.force_authenticate(user=self.customer)
        self.client.post(reverse('marketing:reviews'), {
            'product_id': self.product.id, 'rating': 5, 'comment': 'Pending moderation',
        }, format='json')
        response = self.client.get(reverse('marketing:reviews') + f'?product={self.product.id}')
        self.assertEqual(len(response.data['results']) if 'results' in response.data else len(response.data), 0)
@override_settings(RETURN_REQUEST_WINDOW_DAYS=7)
class ReturnRequestCreationTests(ReviewsReturnsTestDataMixin, APITestCase):
    def _completed_order_with_item(self, customer, quantity=3):
        order = self._make_order(customer=customer, status_=Order.Status.COMPLETED)
        item = OrderItem.objects.create(
            order=order, product=self.product, quantity=quantity, unit_price=Decimal('1000.00'),
        )
        return order, item
    def test_unauthenticated_rejected(self):
        response = self.client.post(reverse('marketing:returns'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    def test_other_customers_order_not_found(self):
        order, item = self._completed_order_with_item(self.customer)
        self.client.force_authenticate(user=self.other_customer)
        response = self.client.post(reverse('marketing:returns'), {
            'order_number': order.order_number, 'order_item_id': item.id,
            'quantity': 1, 'reason': 'Not mine',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    def test_pending_order_ineligible(self):
        order = self._make_order(customer=self.customer, status_=Order.Status.PENDING)
        item = OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=Decimal('1000.00'))
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:returns'), {
            'order_number': order.order_number, 'order_item_id': item.id,
            'quantity': 1, 'reason': 'Too early',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    def test_successful_return_request_created_pending(self):
        order, item = self._completed_order_with_item(self.customer, quantity=3)
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:returns'), {
            'order_number': order.order_number, 'order_item_id': item.id,
            'quantity': 2, 'reason': 'Wrong size',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], ReturnRequest.ReturnStatus.PENDING)
    def test_quantity_exceeding_order_item_rejected(self):
        order, item = self._completed_order_with_item(self.customer, quantity=2)
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:returns'), {
            'order_number': order.order_number, 'order_item_id': item.id,
            'quantity': 5, 'reason': 'Too many',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    def test_cumulative_over_return_across_requests_blocked(self):
        """3-unit line: request 2 (PENDING), then request 2 more -- only 1 remains eligible."""
        order, item = self._completed_order_with_item(self.customer, quantity=3)
        self.client.force_authenticate(user=self.customer)
        url = reverse('marketing:returns')
        first = self.client.post(url, {
            'order_number': order.order_number, 'order_item_id': item.id,
            'quantity': 2, 'reason': 'Partial return',
        }, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(url, {
            'order_number': order.order_number, 'order_item_id': item.id,
            'quantity': 2, 'reason': 'Second attempt',
        }, format='json')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('1 unit', second.data['error'])
    def test_rejected_return_frees_up_quantity_for_new_request(self):
        order, item = self._completed_order_with_item(self.customer, quantity=2)
        first_return = ReturnRequest.objects.create(
            order=order, order_item=item, quantity=2, reason='Initial',
            status=ReturnRequest.ReturnStatus.REJECTED,
            decided_by=self.manager, decided_at=timezone.now(),
            decision_reason='Initial request rejected.',
        )
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse('marketing:returns'), {
            'order_number': order.order_number, 'order_item_id': item.id,
            'quantity': 2, 'reason': 'Retry after rejection',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
class ReturnDecisionTests(ReviewsReturnsTestDataMixin, APITestCase):
    def _pending_return(self, quantity=2, branch=None):
        order, item = None, None
        order = self._make_order(customer=self.customer, status_=Order.Status.COMPLETED, branch=branch or self.branch)
        item = OrderItem.objects.create(order=order, product=self.product, quantity=quantity, unit_price=Decimal('1000.00'))
        from inventory.models import Stock
        Stock.objects.get_or_create(branch=order.branch, product=self.product, defaults={'quantity': 10})
        return ReturnRequest.objects.create(order=order, order_item=item, quantity=quantity, reason='Test reason')
    def test_customer_cannot_decide(self):
        ret = self._pending_return()
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            reverse('marketing:return-decide', kwargs={'return_id': ret.id}),
            {
                'decision': 'APPROVED', 'reason': 'Approved after inspection.',
                'item_condition': 'DAMAGED', 'stock_disposition': 'QUARANTINED',
                'refund_status': 'PENDING_MANUAL',
            }, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    def test_manager_from_other_branch_rejected(self):
        ret = self._pending_return(branch=self.branch)
        self.client.force_authenticate(user=self.other_manager)
        response = self.client.post(
            reverse('marketing:return-decide', kwargs={'return_id': ret.id}),
            {
                'decision': 'APPROVED', 'reason': 'Approved after inspection.',
                'item_condition': 'DAMAGED', 'stock_disposition': 'QUARANTINED',
                'refund_status': 'PENDING_MANUAL',
            }, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    def test_same_branch_manager_approves_and_restocks(self):
        from inventory.models import Stock
        ret = self._pending_return(quantity=2, branch=self.branch)
        stock_before = Stock.objects.get(branch=self.branch, product=self.product).quantity
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            reverse('marketing:return-decide', kwargs={'return_id': ret.id}),
            {
                'decision': 'APPROVED', 'reason': 'Damage confirmed by manager.',
                'item_condition': 'DAMAGED', 'stock_disposition': 'QUARANTINED',
                'refund_status': 'PENDING_MANUAL',
            }, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ReturnRequest.ReturnStatus.APPROVED)
        stock = Stock.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(stock.quantity, stock_before)
        self.assertEqual(stock.damaged_quantity, 2)
    def test_manager_rejects_no_restock(self):
        from inventory.models import Stock
        ret = self._pending_return(quantity=2, branch=self.branch)
        stock_before = Stock.objects.get(branch=self.branch, product=self.product).quantity
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            reverse('marketing:return-decide', kwargs={'return_id': ret.id}),
            {'decision': 'REJECTED', 'reason': 'Item is outside the approved policy.'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stock_after = Stock.objects.get(branch=self.branch, product=self.product).quantity
        self.assertEqual(stock_after, stock_before)
    def test_already_decided_return_rejected(self):
        ret = self._pending_return(branch=self.branch)
        ret.status = ReturnRequest.ReturnStatus.APPROVED
        ret.decided_by = self.manager
        ret.decided_at = timezone.now()
        ret.decision_reason = 'Previously approved.'
        ret.save()
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            reverse('marketing:return-decide', kwargs={'return_id': ret.id}),
            {'decision': 'REJECTED', 'reason': 'Duplicate decision attempt.'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    def test_branch_queue_scoped_to_manager_branch(self):
        ret_own = self._pending_return(branch=self.branch)
        ret_other = self._pending_return(branch=self.other_branch)
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(reverse('marketing:returns-branch'))
        ids = [r['id'] for r in response.data]
        self.assertIn(ret_own.id, ids)
        self.assertNotIn(ret_other.id, ids)
    def test_super_admin_sees_all_branches_queue(self):
        super_admin = User.objects.create_user(
            username='rrsuperadmin0001', phone_number='+254799200005',
            email='rrsuperadmin0001@test.com', password='SuperPass123!',
            role=User.Role.SUPER_ADMIN, is_staff=True, is_superuser=True,
        )
        ret_a = self._pending_return(branch=self.branch)
        ret_b = self._pending_return(branch=self.other_branch)
        self.client.force_authenticate(user=super_admin)
        response = self.client.get(reverse('marketing:returns-branch'))
        ids = [r['id'] for r in response.data]
        self.assertIn(ret_a.id, ids)
        self.assertIn(ret_b.id, ids)
