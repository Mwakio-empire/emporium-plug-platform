from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import hashlib
import hmac

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from analytics.models import AuditLog
from analytics.services import AuditTrackingService
from inventory.models import StockAuditLog
from inventory.services import InventoryService
from orders.models import Order, OrderItem
from users.models import User

from .models import Coupon, CouponRedemption, FlashSale, ProductReview, ReturnRequest


MONEY = Decimal('0.01')


class PromotionService:
    """Concurrency-safe coupon redemption and promotional price resolution."""

    @staticmethod
    def _validate_stacking_policy(*, coupon, pricing_sources):
        sources = {str(source) for source in pricing_sources if source}
        if OrderItem.PricingSource.WHOLESALE in sources:
            raise ValidationError(
                'A quantity price is already applied. Coupons cannot be combined with quantity pricing.'
            )
        if (
            OrderItem.PricingSource.FLASH_SALE in sources
            and not coupon.allow_discounted_items
        ):
            raise ValidationError(
                'This coupon cannot be combined with products that are already discounted.'
            )

    @staticmethod
    def _customer_key(*, customer=None, phone=''):
        identity = f'user:{customer.pk}' if customer else f'phone:{str(phone or "").strip()}'
        return hmac.new(
            settings.SECRET_KEY.encode('utf-8'), identity.encode('utf-8'), hashlib.sha256,
        ).hexdigest()

    @classmethod
    @transaction.atomic
    def validate_and_apply_coupon_campaign(cls, order: Order, coupon_code: str) -> Order:
        order = Order.objects.select_for_update(of=('self',)).select_related(
            'customer', 'branch',
        ).get(pk=order.pk)
        existing = CouponRedemption.objects.select_related('coupon').filter(order=order).first()
        normalized_code = str(coupon_code or '').strip().upper()
        if existing:
            if existing.coupon.code == normalized_code:
                return order
            raise ValidationError('Only one coupon may be applied to an order.')
        if order.discount_amount > 0:
            raise ValidationError('Coupons cannot be combined with a manual discount.')

        try:
            coupon = Coupon.objects.select_for_update().get(code=normalized_code)
        except Coupon.DoesNotExist:
            raise ValidationError('This coupon is inactive, expired, or invalid.') from None

        cls._validate_stacking_policy(
            coupon=coupon,
            pricing_sources=order.items.values_list('pricing_source', flat=True),
        )

        now = timezone.now()
        if (
            not coupon.is_active
            or not (coupon.active_from <= now <= coupon.active_to)
            or coupon.times_used >= coupon.usage_limit
        ):
            raise ValidationError('This coupon is inactive, expired, or invalid.')
        if coupon.branches.exists() and not coupon.branches.filter(pk=order.branch_id).exists():
            raise ValidationError('This coupon is not available for this order.')
        if order.subtotal < coupon.min_order_value:
            raise ValidationError('Order total is below the required minimum threshold.')
        customer_key = cls._customer_key(customer=order.customer, phone=order.customer_phone)
        if CouponRedemption.objects.filter(
            coupon=coupon, customer_key=customer_key,
        ).count() >= coupon.per_customer_limit:
            raise ValidationError('You have already reached this coupon’s usage limit.')

        if coupon.discount_type == Coupon.DiscountType.FIXED:
            discount = coupon.value
        else:
            discount = (coupon.value * order.subtotal / Decimal('100')).quantize(
                MONEY, rounding=ROUND_HALF_UP,
            )
        discount = min(discount, order.subtotal).quantize(MONEY)
        order.discount_amount = discount
        order.total_payable = order.subtotal - discount + order.delivery_fee
        order.save(update_fields=['discount_amount', 'total_payable', 'updated_at'])
        CouponRedemption.objects.create(
            coupon=coupon, order=order, customer=order.customer,
            customer_key=customer_key, discount_amount=discount,
        )
        coupon.times_used += 1
        coupon.save(update_fields=['times_used'])
        AuditTrackingService.log_action(
            user=order.processed_by,
            action_type=AuditLog.ActionTypes.PROMOTION_REDEMPTION,
            description=(
                f'coupon_id={coupon.pk}; order_id={order.pk}; branch_id={order.branch_id}; '
                f'discount={discount}'
            ),
        )
        return order

    @classmethod
    def validate_coupon_preview(
        cls, *, coupon_code, subtotal, branch, customer=None, pricing_sources=(),
    ):
        """Validate without consuming a redemption or mutating counters."""
        now = timezone.now()
        try:
            coupon = Coupon.objects.get(code=str(coupon_code or '').strip().upper())
        except Coupon.DoesNotExist:
            raise ValidationError('This coupon is inactive, expired, or invalid.') from None
        cls._validate_stacking_policy(
            coupon=coupon,
            pricing_sources=pricing_sources,
        )
        if (
            not coupon.is_active
            or not (coupon.active_from <= now <= coupon.active_to)
            or coupon.times_used >= coupon.usage_limit
        ):
            raise ValidationError('This coupon is inactive, expired, or invalid.')
        if coupon.branches.exists() and not coupon.branches.filter(pk=branch.pk).exists():
            raise ValidationError('This coupon is not available for this order.')
        subtotal = Decimal(subtotal)
        if subtotal < coupon.min_order_value:
            raise ValidationError('Order total is below the required minimum threshold.')
        if customer and customer.is_authenticated and CouponRedemption.objects.filter(
            coupon=coupon, customer_key=cls._customer_key(customer=customer),
        ).count() >= coupon.per_customer_limit:
            raise ValidationError('You have already reached this coupon’s usage limit.')
        discount = (
            coupon.value if coupon.discount_type == Coupon.DiscountType.FIXED
            else (coupon.value * subtotal / Decimal('100')).quantize(MONEY, rounding=ROUND_HALF_UP)
        )
        return min(discount, subtotal).quantize(MONEY)

    @classmethod
    def resolve_live_variant_market_price(cls, variant) -> Decimal:
        now = timezone.now()
        active_sale = FlashSale.objects.filter(
            variant=variant, start_time__lte=now, end_time__gte=now, is_active=True,
        ).order_by('sale_price', 'pk').first()
        if active_sale:
            return active_sale.sale_price
        return getattr(variant, 'price', None) or variant.product.price


class FeedbackService:
    SUCCESSFUL_SALE_STATUSES = [
        Order.Status.COMPLETED,
        Order.Status.DELIVERED,
        Order.Status.CUSTOMER_CONFIRMED,
        Order.Status.COLLECTED,
    ]

    @classmethod
    def _has_completed_purchase(cls, product, customer) -> bool:
        phone = getattr(customer, 'phone_number', '') or ''
        return Order.objects.filter(
            Q(customer=customer) | Q(customer_phone=phone),
            status__in=cls.SUCCESSFUL_SALE_STATUSES,
        ).filter(
            Q(items__product=product) | Q(items__variant__product=product),
        ).exists()

    @classmethod
    @transaction.atomic
    def submit_customer_product_review(cls, product, customer, rating: int, comment: str) -> ProductReview:
        if not cls._has_completed_purchase(product, customer):
            raise ValidationError('Only confirmed purchasers may review this product.')
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise ValidationError('Choose a rating from 1 to 5.') from None
        comment = str(comment or '').strip()
        if rating not in range(1, 6):
            raise ValidationError('Choose a rating from 1 to 5.')
        if len(comment) < 5:
            raise ValidationError('Write at least five characters about the product.')
        try:
            return ProductReview.objects.create(
                product=product,
                customer=customer,
                rating=rating,
                comment=comment,
                is_verified_purchase=True,
                is_approved=False,
            )
        except IntegrityError:
            raise ValidationError('You have already reviewed this product.') from None

    @classmethod
    @transaction.atomic
    def moderate_review(cls, *, review_id, approved, moderator, reason):
        if moderator.role not in {User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN}:
            raise ValidationError('Only a manager may moderate reviews.')
        reason = str(reason or '').strip()
        if len(reason) < 5:
            raise ValidationError('Record a moderation reason of at least five characters.')
        review = ProductReview.objects.select_for_update().get(pk=review_id)
        if review.moderated_at is not None:
            raise ValidationError('This review has already been moderated.')
        review.is_approved = bool(approved)
        review.moderated_by = moderator
        review.moderated_at = timezone.now()
        review.moderation_reason = reason
        review.save(update_fields=[
            'is_approved', 'moderated_by', 'moderated_at', 'moderation_reason',
        ])
        AuditTrackingService.log_action(
            user=moderator,
            action_type=AuditLog.ActionTypes.REVIEW_MODERATION,
            description=(
                f'review_id={review.pk}; product_id={review.product_id}; '
                f'decision={"APPROVED" if approved else "REJECTED"}'
            ),
        )
        return review


class ReturnProcessingService:
    ELIGIBLE_STATUSES = [
        Order.Status.COMPLETED,
        Order.Status.DELIVERED,
        Order.Status.CUSTOMER_CONFIRMED,
        Order.Status.COLLECTED,
    ]

    @classmethod
    @transaction.atomic
    def create_return_request(cls, *, order_number, order_item_id, quantity, reason, customer):
        window_days = int(getattr(settings, 'RETURN_REQUEST_WINDOW_DAYS', 0))
        if window_days <= 0:
            raise ValidationError('Online return requests are not enabled until the client approves a return window.')
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number,
                customer=customer,
                status__in=cls.ELIGIBLE_STATUSES,
            )
        except Order.DoesNotExist:
            raise ValidationError('Order not found, not yours, or not eligible for return.') from None
        try:
            order_item = OrderItem.objects.select_for_update().get(pk=order_item_id, order=order)
        except OrderItem.DoesNotExist:
            raise ValidationError('Order item not found on this order.') from None
        product = order_item.variant.product if order_item.variant_id else order_item.product
        if product.customer_return_policy != product.CustomerReturnPolicy.SEVEN_DAY:
            raise ValidationError(
                'This item is not eligible for online return requests. Contact customer support if it is wrong or defective.'
            )
        completed_event = order.status_history.filter(
            new_status__in=cls.ELIGIBLE_STATUSES,
        ).order_by('-created_at').first()
        completed_at = completed_event.created_at if completed_event else order.updated_at
        if timezone.now() > completed_at + timedelta(days=window_days):
            raise ValidationError(f'The {window_days}-day return request window has expired.')
        quantity = int(quantity)
        already_requested = ReturnRequest.objects.filter(
            order_item=order_item,
            status__in=[ReturnRequest.ReturnStatus.PENDING, ReturnRequest.ReturnStatus.APPROVED],
        ).aggregate(total=Sum('quantity'))['total'] or 0
        remaining = order_item.quantity - already_requested
        if quantity <= 0 or quantity > remaining:
            raise ValidationError(f'Only {remaining} unit(s) of this item are eligible for return.')
        reason = str(reason or '').strip()
        if len(reason) < 5:
            raise ValidationError('Explain the return reason using at least five characters.')
        return ReturnRequest.objects.create(
            order=order, order_item=order_item, quantity=quantity, reason=reason,
        )

    @classmethod
    @transaction.atomic
    def evaluate_and_finalize_return(
        cls, *, return_request_id, target_status, manager_user, decision_reason,
        item_condition=ReturnRequest.ItemCondition.UNKNOWN,
        stock_disposition='', refund_status=ReturnRequest.RefundStatus.NOT_REQUIRED,
    ) -> ReturnRequest:
        if manager_user.role not in {User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN}:
            raise ValidationError('Only a branch manager or super admin may decide returns.')
        if target_status not in {ReturnRequest.ReturnStatus.APPROVED, ReturnRequest.ReturnStatus.REJECTED}:
            raise ValidationError('Return decision must be approved or rejected.')
        decision_reason = str(decision_reason or '').strip()
        if len(decision_reason) < 5:
            raise ValidationError('Record a decision reason of at least five characters.')
        request = ReturnRequest.objects.select_for_update(of=('self',)).select_related(
            'order__branch', 'order_item__variant__product', 'order_item__product',
        ).get(pk=return_request_id)
        if request.status != ReturnRequest.ReturnStatus.PENDING:
            raise ValidationError('This return has already been finalized.')
        if (
            manager_user.role == User.Role.BRANCH_MANAGER
            and manager_user.branch_id != request.order.branch_id
        ):
            raise ValidationError('This return belongs to a different branch.')

        if target_status == ReturnRequest.ReturnStatus.APPROVED:
            if item_condition == ReturnRequest.ItemCondition.UNKNOWN:
                raise ValidationError('Assess the returned item condition before approval.')
            if stock_disposition not in ReturnRequest.StockDisposition.values:
                raise ValidationError('Choose how approved stock should be handled.')
            item = request.order_item
            inventory_kwargs = {
                'branch': request.order.branch,
                'quantity': int(request.quantity),
                'triggered_by': manager_user,
                'variant': item.variant,
                'product': item.product,
                'reference_number': f'RET-{request.pk}',
                'note': f'Return {request.pk}: {decision_reason}',
            }
            if stock_disposition == ReturnRequest.StockDisposition.SELLABLE:
                InventoryService.adjust_stock(
                    branch=inventory_kwargs['branch'],
                    change_amount=inventory_kwargs['quantity'],
                    reason=StockAuditLog.Reason.RETURN,
                    triggered_by=manager_user,
                    variant=item.variant,
                    product=item.product,
                    reference_number=inventory_kwargs['reference_number'],
                    note=inventory_kwargs['note'],
                )
            else:
                InventoryService.quarantine_return(**inventory_kwargs)
        else:
            stock_disposition = ''
            if refund_status == ReturnRequest.RefundStatus.PENDING_MANUAL:
                raise ValidationError('A rejected return cannot have a pending refund.')

        request.status = target_status
        request.item_condition = item_condition
        request.stock_disposition = stock_disposition
        request.refund_status = refund_status
        request.decision_reason = decision_reason
        request.decided_by = manager_user
        request.decided_at = timezone.now()
        request.save(update_fields=[
            'status', 'item_condition', 'stock_disposition', 'refund_status',
            'decision_reason', 'decided_by', 'decided_at',
        ])
        AuditTrackingService.log_action(
            user=manager_user,
            action_type=AuditLog.ActionTypes.RETURN_DECISION,
            description=(
                f'return_id={request.pk}; order_id={request.order_id}; '
                f'branch_id={request.order.branch_id}; decision={target_status}; '
                f'disposition={stock_disposition or "NONE"}; refund_status={refund_status}'
            ),
        )
        return request
