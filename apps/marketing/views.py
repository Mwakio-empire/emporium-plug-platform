import logging
from django.core.exceptions import ValidationError
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from catalog.models import Product
from users.models import User
from users.permissions import IsBranchManagerOrAbove, IsCustomerRole
from users.rate_limit import check_rate_limit
from .models import ProductReview, ReturnRequest
from .serializers import (
    ProductReviewCreateSerializer, ProductReviewSerializer,
    ReturnRequestCreateSerializer, ReturnRequestSerializer,
    ReturnDecisionSerializer, ReviewModerationSerializer,
)
from .services import FeedbackService, ReturnProcessingService
logger = logging.getLogger(__name__)
class ProductReviewListCreateView(generics.ListCreateAPIView):
    """
    GET  /marketing/reviews/?product=<id>  -- public, approved reviews only
    POST /marketing/reviews/                -- customer submits a review
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsCustomerRole()]
        return [AllowAny()]
    def get_serializer_class(self):
        return (
            ProductReviewCreateSerializer if self.request.method == 'POST'
            else ProductReviewSerializer
        )
    def get_queryset(self):
        qs = ProductReview.objects.filter(
            is_approved=True, is_current=True,
        ).select_related('customer', 'product')
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs
    def create(self, request, *args, **kwargs):
        serializer = ProductReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            product = Product.objects.get(id=v['product_id'])
        except Product.DoesNotExist:
            return Response({'error': 'Invalid product_id.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            check_rate_limit(
                f'review_submit:{request.user.pk}', limit=5, window_seconds=3600,
            )
            review = FeedbackService.submit_customer_product_review(
                product=product, customer=request.user,
                rating=v['rating'], comment=v['comment'],
            )
        except ValidationError as e:
            message = e.messages[0] if hasattr(e, 'messages') else str(e)
            return Response(
                {'error': message},
                status=(
                    status.HTTP_429_TOO_MANY_REQUESTS if 'Too many attempts' in message
                    else status.HTTP_400_BAD_REQUEST if 'already reviewed' in message
                    else status.HTTP_403_FORBIDDEN
                ),
            )
        return Response(ProductReviewSerializer(review).data, status=status.HTTP_201_CREATED)
class MyReturnRequestListCreateView(generics.ListCreateAPIView):
    """
    GET  /marketing/returns/   -- customer's own return requests
    POST /marketing/returns/   -- customer raises a return
    """
    permission_classes = [IsCustomerRole]
    serializer_class = ReturnRequestSerializer
    def get_queryset(self):
        return ReturnRequest.objects.filter(
            order__customer=self.request.user
        ).select_related('order__branch', 'order_item__variant__product', 'order_item__product')
    def create(self, request, *args, **kwargs):
        serializer = ReturnRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            return_request = ReturnProcessingService.create_return_request(
                order_number=v['order_number'], order_item_id=v['order_item_id'],
                quantity=v['quantity'], reason=v['reason'], customer=request.user,
            )
        except ValidationError as exc:
            message = exc.messages[0] if hasattr(exc, 'messages') else str(exc)
            not_found = message.startswith(('Order not found', 'Order item not found'))
            return Response(
                {'error': message},
                status=status.HTTP_404_NOT_FOUND if not_found else status.HTTP_400_BAD_REQUEST,
            )
        logger.info(
            "Return request raised | ReturnID=%s | OrderID=%s | CustomerID=%s",
            return_request.pk, return_request.order_id, request.user.pk,
        )
        return Response(ReturnRequestSerializer(return_request).data, status=status.HTTP_201_CREATED)

class BranchReturnRequestListView(generics.ListAPIView):
    """GET /marketing/returns/branch/ -- manager's branch pending-returns queue."""
    permission_classes = [IsBranchManagerOrAbove]
    serializer_class = ReturnRequestSerializer
    pagination_class = None
    def get_queryset(self):
        qs = ReturnRequest.objects.filter(
            status=ReturnRequest.ReturnStatus.PENDING,
        ).select_related('order__branch', 'order_item__variant__product', 'order_item__product')
        if self.request.user.role == User.Role.BRANCH_MANAGER:
            qs = qs.filter(order__branch=self.request.user.branch)
        return qs
class ReturnRequestDecisionView(APIView):
    """
    POST /marketing/returns/<id>/decide/
    Manager approves or rejects. Approval triggers atomic stock restoration
    via ReturnProcessingService. BRANCH_MANAGER is restricted to returns on
    orders at their own branch; SUPER_ADMIN is unrestricted.
    """
    permission_classes = [IsBranchManagerOrAbove]
    def post(self, request, return_id):
        serializer = ReturnDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data['decision']
        try:
            return_request = ReturnRequest.objects.select_related('order__branch').get(id=return_id)
        except ReturnRequest.DoesNotExist:
            return Response({'error': 'Return request not found.'}, status=status.HTTP_404_NOT_FOUND)
        if (
            request.user.role == User.Role.BRANCH_MANAGER
            and return_request.order.branch_id != request.user.branch_id
        ):
            return Response(
                {'error': 'This return belongs to a different branch.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        target_status = (
            ReturnRequest.ReturnStatus.APPROVED if decision == 'APPROVED'
            else ReturnRequest.ReturnStatus.REJECTED
        )
        try:
            finalized = ReturnProcessingService.evaluate_and_finalize_return(
                return_request_id=return_request.id,
                target_status=target_status,
                manager_user=request.user,
                decision_reason=serializer.validated_data['reason'],
                item_condition=serializer.validated_data['item_condition'],
                stock_disposition=serializer.validated_data['stock_disposition'],
                refund_status=serializer.validated_data['refund_status'],
            )
        except ValidationError as e:
            return Response(
                {'error': e.message if hasattr(e, 'message') else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ReturnRequestSerializer(finalized).data)


class ReviewModerationQueueView(generics.ListAPIView):
    permission_classes = [IsBranchManagerOrAbove]
    serializer_class = ProductReviewSerializer
    pagination_class = None

    def get_queryset(self):
        return ProductReview.objects.filter(
            moderated_at__isnull=True,
        ).select_related('customer', 'product').order_by('created_at')


class ReviewModerationDecisionView(APIView):
    permission_classes = [IsBranchManagerOrAbove]

    def post(self, request, review_id):
        serializer = ReviewModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            review = FeedbackService.moderate_review(
                review_id=review_id,
                approved=serializer.validated_data['decision'] == 'APPROVED',
                moderator=request.user,
                reason=serializer.validated_data['reason'],
            )
        except ProductReview.DoesNotExist:
            return Response({'error': 'Review not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProductReviewSerializer(review).data)
