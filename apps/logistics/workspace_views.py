from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from branches.models import Branch
from orders.models import Order
from users.models import User
from users.permissions import is_rider
from users.rate_limit import check_rate_limit

from .fulfilment_services import FulfilmentService
from .models import PackingChecklist, PackingChecklistItem, ParcelDispatch, RiderProfile


FULFILMENT_ROLES = {
    User.Role.STAFF,
    User.Role.INVENTORY_MANAGER,
    User.Role.BRANCH_MANAGER,
    User.Role.SUPER_ADMIN,
}


def _message(exc):
    return exc.messages[0] if hasattr(exc, 'messages') else str(exc)


def _branch(request):
    if request.user.role != User.Role.SUPER_ADMIN:
        return request.user.branch
    raw = request.POST.get('workspace_branch') or request.GET.get('branch')
    if raw:
        return Branch.objects.filter(pk=raw, is_active=True).first()
    return Branch.objects.filter(is_active=True).order_by('name').first()


def _redirect(branch):
    url = reverse('logistics:fulfilment-workspace')
    return redirect(f'{url}?branch={branch.pk}' if branch else url)


class FulfilmentAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_active and user.role in FULFILMENT_ROLES and not is_rider(user)


class FulfilmentWorkspaceView(FulfilmentAccessMixin, TemplateView):
    template_name = 'logistics/fulfilment_workspace.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = _branch(self.request)
        context['active_branch'] = branch
        context['branches'] = Branch.objects.filter(is_active=True).order_by('name')
        if branch:
            context['orders'] = Order.objects.filter(
                branch=branch,
                order_type__in=[Order.OrderType.ONLINE_DELIVERY, Order.OrderType.ONLINE_PICKUP],
            ).exclude(status__in=[
                Order.Status.CANCELLED, Order.Status.COLLECTED,
                Order.Status.CUSTOMER_CONFIRMED, Order.Status.RETURNED,
            ]).select_related(
                'branch', 'pickup_slot', 'delivery_zone', 'parcel_destination__county',
                'parcel_dispatch', 'delivery_quote_request',
                'packing_checklist', 'delivery_assignment__rider__user',
            ).prefetch_related(
                'items__product', 'items__variant__product',
                'packing_checklist__lines__order_item__product',
                'packing_checklist__lines__order_item__variant__product',
            ).order_by('created_at')
            context['riders'] = RiderProfile.objects.filter(
                branch=branch, status=RiderProfile.DutyStatus.AVAILABLE,
            ).select_related('user').order_by('user__first_name', 'user__username')
        return context


class PackingStartView(FulfilmentAccessMixin, View):
    def post(self, request, order_id):
        branch = _branch(request)
        try:
            FulfilmentService.start_packing(
                order_id=order_id, actor=request.user, note=request.POST.get('note', ''),
            )
        except (ValidationError, Order.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, 'Packing checklist started.')
        return _redirect(branch)


class PackingLineCheckView(FulfilmentAccessMixin, View):
    def post(self, request, checklist_id, line_id):
        branch = _branch(request)
        try:
            FulfilmentService.check_line(
                checklist_id=checklist_id, line_id=line_id, actor=request.user,
            )
        except (ValidationError, PackingChecklist.DoesNotExist, PackingChecklistItem.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, 'Packing line checked.')
        return _redirect(branch)


class PackingCompleteView(FulfilmentAccessMixin, View):
    def post(self, request, checklist_id):
        branch = _branch(request)
        try:
            FulfilmentService.complete_packing(checklist_id=checklist_id, actor=request.user)
        except (ValidationError, PackingChecklist.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, 'Parcel packed and sealed.')
        return _redirect(branch)


class PickupReadyView(FulfilmentAccessMixin, View):
    def post(self, request, order_id):
        branch = _branch(request)
        try:
            order = FulfilmentService.mark_ready_for_pickup(order_id=order_id, actor=request.user)
        except (ValidationError, Order.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'{order.order_number} is ready for S18 pickup.')
        return _redirect(branch)


class RiderAssignWorkspaceView(FulfilmentAccessMixin, View):
    def post(self, request, order_number):
        branch = _branch(request)
        try:
            assignment, _ = FulfilmentService.assign_rider(
                order_number=order_number,
                rider_profile_id=request.POST.get('rider_profile_id'),
                actor=request.user,
            )
        except (ValidationError, Order.DoesNotExist, RiderProfile.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'Rider assigned to {assignment.order.order_number}.')
        return _redirect(branch)


class PickupConfirmWorkspaceView(FulfilmentAccessMixin, View):
    def post(self, request):
        branch = _branch(request)
        try:
            check_rate_limit(
                f"pickup_verify:{request.user.pk}:{request.META.get('REMOTE_ADDR', 'unknown')}",
                limit=10,
                window_seconds=300,
            )
            order = FulfilmentService.confirm_pickup(
                pickup_code=request.POST.get('pickup_code'), actor=request.user,
            )
        except ValidationError as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'{order.order_number} collected successfully.')
        return _redirect(branch)


class ParcelDispatchWorkspaceView(FulfilmentAccessMixin, View):
    def post(self, request, order_id):
        branch = _branch(request)
        try:
            _, order = FulfilmentService.dispatch_parcel(
                order_id=order_id,
                actor=request.user,
                parcel_reference=request.POST.get('parcel_reference'),
                actual_transport_cost=request.POST.get('actual_transport_cost'),
                vehicle_registration=request.POST.get('vehicle_registration'),
                operator_contact=request.POST.get('operator_contact'),
                dispatch_note=request.POST.get('dispatch_note'),
            )
        except (ValidationError, Order.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'{order.order_number} dispatched to {order.parcel_town}.')
        return _redirect(branch)


class ParcelArrivedWorkspaceView(FulfilmentAccessMixin, View):
    def post(self, request, order_id):
        branch = _branch(request)
        try:
            order = FulfilmentService.mark_parcel_arrived(order_id=order_id, actor=request.user)
        except (ValidationError, Order.DoesNotExist, ParcelDispatch.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'{order.order_number} marked arrived at destination.')
        return _redirect(branch)


class ParcelCollectedWorkspaceView(FulfilmentAccessMixin, View):
    def post(self, request, order_id):
        branch = _branch(request)
        try:
            order = FulfilmentService.mark_parcel_collected(
                order_id=order_id, actor=request.user,
                confirmation_note=request.POST.get('confirmation_note'),
            )
        except (ValidationError, Order.DoesNotExist, ParcelDispatch.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'{order.order_number} parcel collection recorded.')
        return _redirect(branch)
