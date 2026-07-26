from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from catalog.models import Product
from orders.models import Order
from users.models import User

from .models import ProductReview, ReturnRequest
from .services import FeedbackService, ReturnProcessingService


def _error(exc):
    return exc.messages[0] if hasattr(exc, 'messages') else str(exc)


class CustomerAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.role == User.Role.CUSTOMER


class ManagerAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.role in {
            User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN,
        }


class CustomerReturnsPageView(CustomerAccessMixin, TemplateView):
    template_name = 'marketing/customer_returns.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['window_days'] = int(getattr(settings, 'RETURN_REQUEST_WINDOW_DAYS', 0))
        orders = list(Order.objects.filter(
            customer=self.request.user,
            status__in=ReturnProcessingService.ELIGIBLE_STATUSES,
        ).select_related('branch').prefetch_related(
            'items__product', 'items__variant__product', 'items__returned_items',
        ).order_by('-updated_at'))
        counted_statuses = {
            ReturnRequest.ReturnStatus.PENDING, ReturnRequest.ReturnStatus.APPROVED,
        }
        for order in orders:
            order.returnable_items = []
            for item in order.items.all():
                product = item.variant.product if item.variant_id else item.product
                if product.customer_return_policy != Product.CustomerReturnPolicy.SEVEN_DAY:
                    continue
                requested = sum(
                    request.quantity for request in item.returned_items.all()
                    if request.status in counted_statuses
                )
                item.remaining_return_quantity = item.quantity - requested
                if item.remaining_return_quantity > 0:
                    order.returnable_items.append(item)
        context['orders'] = orders
        context['return_requests'] = ReturnRequest.objects.filter(
            order__customer=self.request.user,
        ).select_related(
            'order__branch', 'order_item__product', 'order_item__variant__product',
        ).order_by('-created_at')
        return context


class CustomerReturnCreateView(CustomerAccessMixin, View):
    def post(self, request):
        try:
            created = ReturnProcessingService.create_return_request(
                order_number=request.POST.get('order_number'),
                order_item_id=request.POST.get('order_item_id'),
                quantity=request.POST.get('quantity'),
                reason=request.POST.get('reason'),
                customer=request.user,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            messages.error(request, _error(exc))
        else:
            messages.success(request, f'Return request #{created.pk} submitted for review.')
        return redirect('marketing:my-returns')


class CustomerReviewCreateView(CustomerAccessMixin, View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        try:
            FeedbackService.submit_customer_product_review(
                product=product, customer=request.user,
                rating=int(request.POST.get('rating', 0)),
                comment=request.POST.get('comment', ''),
            )
        except (ValidationError, ValueError) as exc:
            messages.error(request, _error(exc))
        else:
            messages.success(request, 'Thank you. Your review is awaiting moderation.')
        return redirect('core:product_detail', slug=product.slug)


class MarketingWorkspaceView(ManagerAccessMixin, TemplateView):
    template_name = 'marketing/operations_workspace.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reviews'] = ProductReview.objects.filter(
            moderated_at__isnull=True, is_current=True,
        ).select_related('product', 'customer').order_by('created_at')
        returns = ReturnRequest.objects.filter(
            status=ReturnRequest.ReturnStatus.PENDING,
        ).select_related(
            'order__branch', 'order_item__product', 'order_item__variant__product',
        ).order_by('created_at')
        if self.request.user.role == User.Role.BRANCH_MANAGER:
            returns = returns.filter(order__branch=self.request.user.branch)
        context['returns'] = returns
        context['conditions'] = ReturnRequest.ItemCondition.choices
        context['dispositions'] = ReturnRequest.StockDisposition.choices
        context['refund_statuses'] = [
            choice for choice in ReturnRequest.RefundStatus.choices
            if choice[0] in {
                ReturnRequest.RefundStatus.NOT_REQUIRED,
                ReturnRequest.RefundStatus.PENDING_MANUAL,
            }
        ]
        return context


class WorkspaceReviewDecisionView(ManagerAccessMixin, View):
    def post(self, request, review_id):
        try:
            FeedbackService.moderate_review(
                review_id=review_id,
                approved=request.POST.get('decision') == 'APPROVED',
                moderator=request.user,
                reason=request.POST.get('reason'),
            )
        except (ValidationError, ProductReview.DoesNotExist) as exc:
            messages.error(request, _error(exc))
        else:
            messages.success(request, 'Review moderation decision recorded.')
        return redirect('marketing:operations-workspace')


class WorkspaceReturnDecisionView(ManagerAccessMixin, View):
    def post(self, request, return_id):
        target = (
            ReturnRequest.ReturnStatus.APPROVED
            if request.POST.get('decision') == 'APPROVED'
            else ReturnRequest.ReturnStatus.REJECTED
        )
        try:
            ReturnProcessingService.evaluate_and_finalize_return(
                return_request_id=return_id,
                target_status=target,
                manager_user=request.user,
                decision_reason=request.POST.get('reason'),
                item_condition=request.POST.get(
                    'item_condition', ReturnRequest.ItemCondition.UNKNOWN,
                ),
                stock_disposition=request.POST.get('stock_disposition', ''),
                refund_status=request.POST.get(
                    'refund_status', ReturnRequest.RefundStatus.NOT_REQUIRED,
                ),
            )
        except (ValidationError, ReturnRequest.DoesNotExist) as exc:
            messages.error(request, _error(exc))
        else:
            messages.success(request, 'Return decision and stock disposition recorded.')
        return redirect('marketing:operations-workspace')
