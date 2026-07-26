from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from orders.models import Order, OrderItem
from marketing.models import Coupon, FlashSale, ProductReview, ReturnRequest
from marketing.services import PromotionService, FeedbackService, ReturnProcessingService

User = get_user_model()

class MarketingPromotionsAndFeedbackMasterTestSuite(TestCase):
    """
    Comprehensive verification suite assessing defensive validations,
    campaign math executions, and restock automations.
    """
    def setUp(self):
        # 1. Topology Setup
        self.branch = Branch.objects.create(name="Nairobi Central Shop", location="CBD")
        
        # 2. RBAC Accounts Setup

        self.super_admin = User.objects.create_superuser(
            username="admin_boss", phone_number="+254711111111",
            email="admin.boss@markettest.ke", password="SecurePassword123",
        )

        self.staff_user = User.objects.create_user(
            username="cashier_jane", phone_number="+254722222222",
            email="cashier.jane@markettest.ke", password="SecurePassword123",
            role=User.Role.STAFF, branch=self.branch,
        )
        self.customer = User.objects.create_user(
            username="buyer_john", phone_number="+254733333333",
            email="buyer.john@markettest.ke", password="SecurePassword123",
            role=User.Role.CUSTOMER,
        )

        # 3. Item Engine Profiles
        self.category = Category.objects.create(name="Apparel")
        self.product = Product.objects.create(name="Designer Safari Suit", category=self.category, price=Decimal('15000.00'))
        self.variant = ProductVariant.objects.create(product=self.product, attribute_name="Size", attribute_value="XL")

        # Initialize Base Branch Storage Levels matching your real model pattern exactly
        self.stock_record = self.variant.stocks.create(branch=self.branch, quantity=50)

        # 4. Standard Order Instantiation Flow
        self.order = Order.objects.create(
            branch=self.branch,
            order_type=Order.OrderType.WALK_IN,
            customer_phone="+254733333333",
            subtotal=Decimal('30000.00'),
            total_payable=Decimal('30000.00'),
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.staff_user,
            status=Order.Status.COMPLETED
        )
        self.order_item = OrderItem.objects.create(
            order=self.order, variant=self.variant, quantity=2, unit_price=Decimal('15000.00')
        )

    def test_coupon_rejection_below_minimum_value_threshold(self):
        """Verifies that coupons are rejected if the order total is below the minimum required amount."""
        restricted_coupon = Coupon.objects.create(
            code="BULK5000",
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('5000.00'),
            active_from=timezone.now() - timedelta(days=1),
            active_to=timezone.now() + timedelta(days=1),
            usage_limit=10,
            min_order_value=Decimal('50000.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            PromotionService.validate_and_apply_coupon_campaign(self.order, "BULK5000")
        self.assertIn("below the required minimum threshold", str(context.exception))

    def test_coupon_rejection_expired_window(self):
        """Verifies that expired coupons are correctly identified and rejected."""
        expired_coupon = Coupon.objects.create(
            code="EXPIRED20",
            discount_type=Coupon.DiscountType.PERCENTAGE,
            value=Decimal('20.00'),
            active_from=timezone.now() - timedelta(days=5),
            active_to=timezone.now() - timedelta(days=1),
            usage_limit=50
        )
        
        with self.assertRaises(ValidationError) as context:
            PromotionService.validate_and_apply_coupon_campaign(self.order, "EXPIRED20")
        self.assertIn("inactive, expired, or invalid", str(context.exception))

    def test_successful_percentage_coupon_recalculation(self):
        """Validates correct discount calculations and ledger updates for percentage-based coupons."""
        valid_coupon = Coupon.objects.create(
            code="SAVE10",
            discount_type=Coupon.DiscountType.PERCENTAGE,
            value=Decimal('10.00'),
            active_from=timezone.now() - timedelta(days=1),
            active_to=timezone.now() + timedelta(days=1),
            usage_limit=100
        )
        
        updated_order = PromotionService.validate_and_apply_coupon_campaign(self.order, "SAVE10")
        self.assertEqual(updated_order.discount_amount, Decimal('3000.00'))
        self.assertEqual(updated_order.total_payable, Decimal('27000.00'))
        
        valid_coupon.refresh_from_db()
        self.assertEqual(valid_coupon.times_used, 1)

    def test_flash_sale_price_resolution(self):
        """Validates that product price evaluation routes to flash sale values during active windows."""
        current_price = PromotionService.resolve_live_variant_market_price(self.variant)
        self.assertEqual(current_price, Decimal('15000.00'))

        FlashSale.objects.create(
            variant=self.variant,
            sale_price=Decimal('11500.00'),
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=2),
            is_active=True
        )

        resolved_price = PromotionService.resolve_live_variant_market_price(self.variant)
        self.assertEqual(resolved_price, Decimal('11500.00'))

    def test_automated_verified_purchase_review_tagging(self):
        """Verifies that product reviews are marked as verified purchases for customers with completed orders."""
        review = FeedbackService.submit_customer_product_review(
            product=self.product, customer=self.customer, rating=5, comment="Exceptional quality stitches!"
        )
        self.assertTrue(review.is_verified_purchase)
        self.assertFalse(review.is_approved)

    def test_return_request_refusal_unauthorized_staff_role(self):
        """Ensures that standard staff profiles cannot authorize item return workflows."""
        ret_request = ReturnRequest.objects.create(
            order=self.order, order_item=self.order_item, quantity=1, reason="Sizing mismatch"
        )
        
        with self.assertRaises(ValidationError) as context:
            ReturnProcessingService.evaluate_and_finalize_return(
                return_request_id=ret_request.id,
                target_status=ReturnRequest.ReturnStatus.APPROVED,
                manager_user=self.staff_user,
                decision_reason='Staff cannot approve this return.',
            )
        self.assertIn("Only a branch manager or super admin", str(context.exception))

    def test_successful_return_approval_and_atomic_restock_sync(self):
        """Validates that approved returns update status records and trigger atomic inventory restorations."""
        ret_request = ReturnRequest.objects.create(
            order=self.order, order_item=self.order_item, quantity=1, reason="Fabric flaw noticed"
        )
        
        self.stock_record.refresh_from_db()
        self.assertEqual(self.stock_record.quantity, 50)

        finalized_request = ReturnProcessingService.evaluate_and_finalize_return(
            return_request_id=ret_request.id,
            target_status=ReturnRequest.ReturnStatus.APPROVED,
            manager_user=self.super_admin,
            decision_reason='Fabric flaw confirmed during inspection.',
            item_condition=ReturnRequest.ItemCondition.DEFECTIVE,
            stock_disposition=ReturnRequest.StockDisposition.QUARANTINED,
            refund_status=ReturnRequest.RefundStatus.PENDING_MANUAL,
        )

        self.assertEqual(finalized_request.status, ReturnRequest.ReturnStatus.APPROVED)
        
        self.stock_record.refresh_from_db()
        self.assertEqual(self.stock_record.quantity, 50)
        self.assertEqual(self.stock_record.damaged_quantity, 1)

    def test_coupon_cannot_stack_with_existing_manual_discount(self):
        """Phase 9 policy: a coupon and manual manager discount cannot stack."""
        self.order.discount_amount = Decimal('3000.00')
        self.order.total_payable = self.order.subtotal - self.order.discount_amount
        self.order.save()
        stacking_coupon = Coupon.objects.create(
            code="STACK2000",
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('2000.00'),
            active_from=timezone.now() - timedelta(days=1),
            active_to=timezone.now() + timedelta(days=1),
            usage_limit=10,
        )
        with self.assertRaises(ValidationError):
            PromotionService.validate_and_apply_coupon_campaign(self.order, "STACK2000")
    def test_coupon_respects_delivery_fee_on_online_order(self):
        """total_payable recompute must add back delivery_fee, not just subtract discount from subtotal."""
        delivery_order = Order.objects.create(
            branch=self.branch,
            order_type=Order.OrderType.ONLINE_DELIVERY,
            customer_phone="+254700111222",
            subtotal=Decimal('5000.00'),
            delivery_fee=Decimal('200.00'),
            total_payable=Decimal('5200.00'),
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.staff_user,
            status=Order.Status.PROCESSING,
        )
        fee_coupon = Coupon.objects.create(
            code="FEEAWARE500",
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('500.00'),
            active_from=timezone.now() - timedelta(days=1),
            active_to=timezone.now() + timedelta(days=1),
            usage_limit=10,
        )
        updated_order = PromotionService.validate_and_apply_coupon_campaign(delivery_order, "FEEAWARE500")
        self.assertEqual(updated_order.discount_amount, Decimal('500.00'))
        self.assertEqual(updated_order.total_payable, Decimal('4700.00'))
    def test_coupon_discount_capped_by_remaining_subtotal(self):
        """A large coupon on a nearly-fully-discounted order caps at the remaining subtotal, never goes negative."""
        oversized_coupon = Coupon.objects.create(
            code="OVERSIZED5000",
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('50000.00'),
            active_from=timezone.now() - timedelta(days=1),
            active_to=timezone.now() + timedelta(days=1),
            usage_limit=10,
        )
        updated_order = PromotionService.validate_and_apply_coupon_campaign(self.order, "OVERSIZED5000")
        self.assertEqual(updated_order.discount_amount, Decimal('30000.00'))
        self.assertEqual(updated_order.total_payable, Decimal('0.00'))
