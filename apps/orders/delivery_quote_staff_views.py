from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from branches.models import Branch
from users.models import User
from users.permissions import is_rider

from .delivery_quote_services import DeliveryQuoteService
from .models import DeliveryQuoteRequest


QUOTE_STAFF_ROLES = {
    User.Role.BRANCH_MANAGER,
    User.Role.SUPER_ADMIN,
}


def _message(exc):
    return exc.messages[0] if hasattr(exc, 'messages') else str(exc)


class DeliveryQuoteStaffMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_active and user.role in QUOTE_STAFF_ROLES and not is_rider(user)

    def active_branch(self):
        if self.request.user.role != User.Role.SUPER_ADMIN:
            return self.request.user.branch
        raw = self.request.POST.get('branch') or self.request.GET.get('branch')
        if raw:
            return Branch.objects.filter(pk=raw, is_active=True).first()
        return Branch.objects.filter(is_active=True).order_by('name').first()

    def quote_queryset(self):
        branch = self.active_branch()
        if branch is None:
            return DeliveryQuoteRequest.objects.none()
        return DeliveryQuoteRequest.objects.filter(branch=branch).select_related(
            'branch', 'customer', 'reviewed_by', 'order',
        )


class DeliveryQuoteWorkspaceView(DeliveryQuoteStaffMixin, TemplateView):
    template_name = 'orders/delivery_quote_workspace.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        quotes = list(self.quote_queryset().exclude(status__in=[
            DeliveryQuoteRequest.Status.ACCEPTED,
            DeliveryQuoteRequest.Status.DECLINED,
            DeliveryQuoteRequest.Status.EXPIRED,
            DeliveryQuoteRequest.Status.CANCELLED,
        ]).order_by('created_at'))
        for quote in quotes:
            quote.is_overdue = (
                quote.status in {
                    DeliveryQuoteRequest.Status.REQUESTED,
                    DeliveryQuoteRequest.Status.REVIEWING,
                }
                and quote.response_due_at < now
            )
        context.update({
            'quotes': quotes,
            'active_branch': self.active_branch(),
            'branches': Branch.objects.filter(is_active=True).order_by('name'),
        })
        return context


class DeliveryQuoteDetailView(DeliveryQuoteStaffMixin, TemplateView):
    template_name = 'orders/delivery_quote_detail.html'

    def get_quote(self):
        quote = self.quote_queryset().filter(reference=self.kwargs['reference']).first()
        if quote is None:
            raise Http404
        return quote

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['quote'] = self.get_quote()
        return context

    def post(self, request, *args, **kwargs):
        quote = self.get_quote()
        try:
            if request.POST.get('action') == 'start_review':
                DeliveryQuoteService.start_review(quote=quote, staff=request.user)
                messages.success(request, 'Quote marked as being reviewed.')
            elif request.POST.get('action') == 'publish':
                DeliveryQuoteService.publish(
                    quote=quote,
                    staff=request.user,
                    transport_operator=request.POST.get('transport_operator'),
                    collection_point=request.POST.get('collection_point'),
                    delivery_fee=request.POST.get('delivery_fee'),
                    expected_arrival=request.POST.get('expected_arrival'),
                )
                messages.success(request, 'Quote published. The customer can now review it.')
            else:
                raise ValidationError('Choose a valid quote action.')
        except ValidationError as exc:
            messages.error(request, _message(exc))
        return redirect(reverse('delivery-quote-detail', args=[quote.reference]))
