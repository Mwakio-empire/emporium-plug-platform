from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from analytics.models import AuditLog
from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock, StockAuditLog
from marketing.models import Coupon, CouponRedemption, ProductReview, ReturnRequest
from marketing.services import FeedbackService, PromotionService, ReturnProcessingService
from orders.models import Order, OrderItem
from users.models import User


class Phase9DataMixin:
    def setUp(self):
        self.branch = Branch.objects.create(name='Phase 9 Branch', location='Nairobi')
        self.other_branch = Branch.objects.create(name='Phase 9 Other', location='Nairobi')
        self.manager = User.objects.create_user(
            username='phase9manager', phone_number='+254700990001',
            email='phase9.manager@example.test', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.customer = User.objects.create_user(
            username='phase9customer', phone_number='+254700990002',
            email='phase9.customer@example.test', password='StrongPass123!',
            first_name='Amina', last_name='Private', role=User.Role.CUSTOMER,
        )
        category = Category.objects.create(name='Phase 9', slug='phase-9')
        self.product = Product.objects.create(
            name='Phase 9 Bag', slug='phase-9-bag', category=category,
            price=Decimal('2000.00'), status=Product.Status.ACTIVE,
            customer_return_policy=Product.CustomerReturnPolicy.SEVEN_DAY,
        )

    def make_order(self, *, branch=None, customer=True, status=Order.Status.COMPLETED):
        order = Order.objects.create(
            branch=branch or self.branch,
            customer=self.customer if customer else None,
            customer_phone=self.customer.phone_number,
            payment_method=Order.PaymentMethod.CASH,
            status=status,
            processed_by=self.manager,
            subtotal=Decimal('4000.00'), total_payable=Decimal('4000.00'),
        )
        item = OrderItem.objects.create(
            order=order, product=self.product, quantity=2,
            unit_price=Decimal('2000.00'),
        )
        return order, item

    def coupon(self, code='P9SAVE'):
        return Coupon.objects.create(
            code=code, discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('500.00'), active_from=timezone.now() - timedelta(hours=1),
            active_to=timezone.now() + timedelta(days=1), usage_limit=5,
            per_customer_limit=1,
        )


class PromotionIntegrityTests(Phase9DataMixin, TestCase):
    def test_redemption_is_idempotent_for_same_order(self):
        order, _ = self.make_order()
        coupon = self.coupon()
        PromotionService.validate_and_apply_coupon_campaign(order, coupon.code)
        PromotionService.validate_and_apply_coupon_campaign(order, coupon.code)
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 1)
        self.assertEqual(CouponRedemption.objects.filter(order=order).count(), 1)

    def test_per_customer_limit_is_enforced(self):
        first, _ = self.make_order()
        second, _ = self.make_order()
        coupon = self.coupon()
        PromotionService.validate_and_apply_coupon_campaign(first, coupon.code)
        with self.assertRaises(ValidationError):
            PromotionService.validate_and_apply_coupon_campaign(second, coupon.code)

    def test_guest_phone_is_covered_by_per_customer_limit(self):
        first, _ = self.make_order(customer=False)
        second, _ = self.make_order(customer=False)
        coupon = self.coupon()
        PromotionService.validate_and_apply_coupon_campaign(first, coupon.code)
        with self.assertRaises(ValidationError):
            PromotionService.validate_and_apply_coupon_campaign(second, coupon.code)

    def test_branch_scope_is_enforced(self):
        order, _ = self.make_order(branch=self.other_branch)
        coupon = self.coupon()
        coupon.branches.add(self.branch)
        with self.assertRaises(ValidationError):
            PromotionService.validate_and_apply_coupon_campaign(order, coupon.code)

    def test_redemption_creates_privileged_audit_entry(self):
        order, _ = self.make_order()
        coupon = self.coupon()
        PromotionService.validate_and_apply_coupon_campaign(order, coupon.code)
        self.assertTrue(AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.PROMOTION_REDEMPTION,
            description__contains=f'order_id={order.pk}',
        ).exists())


class ReviewIntegrityTests(Phase9DataMixin, TestCase):
    def test_database_allows_only_one_current_review(self):
        self.make_order()
        FeedbackService.submit_customer_product_review(
            self.product, self.customer, 5, 'Excellent quality.',
        )
        with self.assertRaises(ValidationError):
            FeedbackService.submit_customer_product_review(
                self.product, self.customer, 3, 'Second review attempt.',
            )

    def test_moderation_records_actor_time_reason_and_audit(self):
        self.make_order()
        review = FeedbackService.submit_customer_product_review(
            self.product, self.customer, 5, 'Excellent quality.',
        )
        review = FeedbackService.moderate_review(
            review_id=review.pk, approved=True, moderator=self.manager,
            reason='Verified constructive review.',
        )
        self.assertTrue(review.is_approved)
        self.assertEqual(review.moderated_by, self.manager)
        self.assertIsNotNone(review.moderated_at)
        self.assertTrue(AuditLog.objects.filter(
            action_type=AuditLog.ActionTypes.REVIEW_MODERATION,
        ).exists())

    def test_public_review_name_does_not_expose_surname(self):
        self.make_order()
        review = FeedbackService.submit_customer_product_review(
            self.product, self.customer, 5, 'Excellent quality.',
        )
        FeedbackService.moderate_review(
            review_id=review.pk, approved=True, moderator=self.manager,
            reason='Suitable for publication.',
        )
        response = self.client.get(reverse('marketing:reviews'), {'product': self.product.pk})
        self.assertContains(response, 'Amina')
        self.assertNotContains(response, 'Private')

    def test_manager_workspace_moderates_review(self):
        self.make_order()
        review = FeedbackService.submit_customer_product_review(
            self.product, self.customer, 4, 'Useful everyday bag.',
        )
        self.client.force_login(self.manager)
        page = self.client.get(reverse('marketing:operations-workspace'))
        self.assertContains(page, 'Useful everyday bag.')
        response = self.client.post(
            reverse('marketing:workspace-review-decide', args=[review.pk]),
            {'decision': 'APPROVED', 'reason': 'Constructive verified review.'},
            follow=True,
        )
        self.assertContains(response, 'Review moderation decision recorded.')
        review.refresh_from_db()
        self.assertTrue(review.is_approved)


class ReturnIntegrityTests(Phase9DataMixin, TestCase):
    @override_settings(RETURN_REQUEST_WINDOW_DAYS=7)
    def test_sellable_return_restores_sellable_stock_with_audit(self):
        order, item = self.make_order()
        stock = Stock.objects.create(branch=self.branch, product=self.product, quantity=3)
        request = ReturnProcessingService.create_return_request(
            order_number=order.order_number, order_item_id=item.pk,
            quantity=1, reason='Wrong colour supplied.', customer=self.customer,
        )
        request = ReturnProcessingService.evaluate_and_finalize_return(
            return_request_id=request.pk,
            target_status=ReturnRequest.ReturnStatus.APPROVED,
            manager_user=self.manager,
            decision_reason='Unused and suitable for resale.',
            item_condition=ReturnRequest.ItemCondition.GOOD,
            stock_disposition=ReturnRequest.StockDisposition.SELLABLE,
            refund_status=ReturnRequest.RefundStatus.PENDING_MANUAL,
        )
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 4)
        self.assertEqual(request.refund_status, ReturnRequest.RefundStatus.PENDING_MANUAL)
        self.assertTrue(StockAuditLog.objects.filter(
            reason=StockAuditLog.Reason.RETURN, reference_number=f'RET-{request.pk}',
        ).exists())

    @override_settings(RETURN_REQUEST_WINDOW_DAYS=7)
    def test_expired_return_window_is_rejected(self):
        order, item = self.make_order()
        Order.objects.filter(pk=order.pk).update(updated_at=timezone.now() - timedelta(days=8))
        with self.assertRaises(ValidationError):
            ReturnProcessingService.create_return_request(
                order_number=order.order_number, order_item_id=item.pk,
                quantity=1, reason='Request submitted too late.', customer=self.customer,
            )

    @override_settings(RETURN_REQUEST_WINDOW_DAYS=7)
    def test_support_only_product_is_not_self_service_returnable(self):
        self.product.customer_return_policy = Product.CustomerReturnPolicy.SUPPORT_ONLY
        self.product.save(update_fields=['customer_return_policy'])
        order, item = self.make_order()
        with self.assertRaisesMessage(ValidationError, 'not eligible for online return requests'):
            ReturnProcessingService.create_return_request(
                order_number=order.order_number, order_item_id=item.pk,
                quantity=1, reason='Wrong item supplied.', customer=self.customer,
            )

    @override_settings(RETURN_REQUEST_WINDOW_DAYS=7)
    def test_customer_page_hides_support_only_product(self):
        self.product.customer_return_policy = Product.CustomerReturnPolicy.SUPPORT_ONLY
        self.product.save(update_fields=['customer_return_policy'])
        self.make_order()
        self.client.force_login(self.customer)
        response = self.client.get(reverse('marketing:my-returns'))
        self.assertNotContains(response, 'Request review')
        self.assertContains(response, 'support-only handling')

    @override_settings(RETURN_REQUEST_WINDOW_DAYS=0)
    def test_return_portal_stays_disabled_without_approved_window(self):
        order, item = self.make_order()
        with self.assertRaises(ValidationError):
            ReturnProcessingService.create_return_request(
                order_number=order.order_number, order_item_id=item.pk,
                quantity=1, reason='Wrong item supplied.', customer=self.customer,
            )

    @override_settings(RETURN_REQUEST_WINDOW_DAYS=0)
    def test_customer_page_explains_disabled_policy(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('marketing:my-returns'))
        self.assertContains(response, 'temporarily unavailable')

    @override_settings(RETURN_REQUEST_WINDOW_DAYS=7)
    def test_customer_page_hides_fully_requested_quantity(self):
        order, item = self.make_order()
        ReturnProcessingService.create_return_request(
            order_number=order.order_number, order_item_id=item.pk,
            quantity=2, reason='Both units were incorrect.', customer=self.customer,
        )
        self.client.force_login(self.customer)
        response = self.client.get(reverse('marketing:my-returns'))
        self.assertContains(response, 'already have an active or approved request')
        self.assertNotContains(response, 'Request review')
