from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from branches.models import Branch
from catalog.models import Product, ProductVariant
from users.models import User

from .intake_services import SupplierIntakeService
from .models import Stock, StockAuditLog, StockCount, StockIntake, TransferRequest
from .operation_services import InventoryOperationsService
from .transfer_services import TransferService


INVENTORY_ROLES = {
    User.Role.INVENTORY_MANAGER,
    User.Role.BRANCH_MANAGER,
    User.Role.SUPER_ADMIN,
}


def _message(exc):
    return exc.messages[0] if hasattr(exc, 'messages') else str(exc)


def _selected_branch(request):
    if request.user.role != User.Role.SUPER_ADMIN:
        return request.user.branch
    raw_branch = request.POST.get('workspace_branch') or request.GET.get('branch')
    if raw_branch:
        return Branch.objects.filter(pk=raw_branch, is_active=True).first()
    return Branch.objects.filter(is_active=True).order_by(
        '-receives_supplier_stock', 'name',
    ).first()


def _workspace_redirect(branch):
    url = reverse('inventory:inventory-workspace')
    return redirect(f'{url}?branch={branch.pk}' if branch else url)


def _resolve_item(item_key):
    prefix, separator, raw_id = (item_key or '').partition(':')
    if not separator or not raw_id.isdigit():
        raise ValidationError('Select a valid catalog item.')
    if prefix == 'p':
        return Product.objects.get(pk=raw_id), None
    if prefix == 'v':
        return None, ProductVariant.objects.select_related('product').get(pk=raw_id)
    raise ValidationError('Select a valid catalog item.')


class InventoryWorkspaceAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.role in INVENTORY_ROLES


class InventoryWorkspaceView(InventoryWorkspaceAccessMixin, TemplateView):
    template_name = 'inventory/workspace.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = _selected_branch(self.request)
        context['active_branch'] = branch
        context['branches'] = Branch.objects.filter(is_active=True).order_by('name')
        simple_products = Product.objects.filter(
            status=Product.Status.ACTIVE, variants__isnull=True,
        ).order_by('name')
        variants = ProductVariant.objects.filter(
            product__status=Product.Status.ACTIVE,
        ).select_related('product').order_by('product__name', 'attribute_name', 'attribute_value')
        context['catalog_choices'] = [
            (f'p:{product.pk}', f'{product.name} - {product.sku}')
            for product in simple_products
        ] + [
            (f'v:{variant.pk}', str(variant)) for variant in variants
        ]
        if branch:
            context['stocks'] = Stock.objects.filter(branch=branch).select_related(
                'product', 'variant__product',
            ).order_by('product__name', 'variant__product__name', 'variant__attribute_value')
            context['transfers'] = TransferRequest.objects.filter(
                Q(from_branch=branch) | Q(to_branch=branch),
            ).select_related(
                'from_branch', 'to_branch', 'product', 'variant__product',
                'requested_by', 'approved_by', 'dispatched_by', 'confirmed_by',
            ).prefetch_related('receipts').order_by('-requested_at')[:50]
            context['intakes'] = StockIntake.objects.filter(branch=branch).select_related(
                'received_by',
            ).prefetch_related('lines')[:20]
            context['open_count'] = StockCount.objects.filter(
                branch=branch, status=StockCount.Status.OPEN,
            ).prefetch_related('lines__product', 'lines__variant__product').first()
        return context


class SupplierIntakeWorkspaceView(InventoryWorkspaceAccessMixin, View):
    def post(self, request):
        branch = _selected_branch(request)
        if not branch:
            raise Http404('Branch not found.')
        item_keys = request.POST.getlist('item')
        quantities = request.POST.getlist('quantity')
        lines = []
        try:
            for item_key, raw_quantity in zip(item_keys, quantities):
                if not item_key and not raw_quantity:
                    continue
                product, variant = _resolve_item(item_key)
                lines.append({
                    'product': product, 'variant': variant,
                    'quantity': int(raw_quantity),
                })
            intake, created = SupplierIntakeService.record_intake(
                branch=branch,
                supplier_name=request.POST.get('supplier_name', ''),
                delivery_reference=request.POST.get('delivery_reference', ''),
                received_by=request.user, lines=lines,
                notes=request.POST.get('notes', ''),
            )
        except (ValidationError, ValueError, Product.DoesNotExist, ProductVariant.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(
                request,
                f"Delivery {intake.delivery_reference} {'recorded' if created else 'was already recorded'}.",
            )
        return _workspace_redirect(branch)


class TransferRequestWorkspaceView(InventoryWorkspaceAccessMixin, View):
    def post(self, request):
        branch = _selected_branch(request)
        try:
            from_branch = Branch.objects.get(pk=request.POST.get('from_branch'), is_active=True)
            to_branch = Branch.objects.get(pk=request.POST.get('to_branch'), is_active=True)
            product, variant = _resolve_item(request.POST.get('item'))
            transfer = TransferService.request_transfer(
                requesting_manager=request.user,
                from_branch=from_branch, to_branch=to_branch,
                quantity=int(request.POST.get('quantity', '0')),
                product=product, variant=variant,
                notes=request.POST.get('notes', ''),
            )
        except (ValidationError, ValueError, Branch.DoesNotExist, Product.DoesNotExist, ProductVariant.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'Transfer #{transfer.pk} requested.')
        return _workspace_redirect(branch)


class TransferActionWorkspaceView(InventoryWorkspaceAccessMixin, View):
    action = None

    def post(self, request, transfer_id):
        branch = _selected_branch(request)
        try:
            if self.action == 'approve':
                transfer = TransferService.approve_transfer(
                    transfer_id=transfer_id, approving_manager=request.user,
                )
            elif self.action == 'dispatch':
                transfer = TransferService.dispatch_transfer(
                    transfer_id=transfer_id, dispatching_manager=request.user,
                )
            elif self.action == 'receive':
                transfer, _ = TransferService.receive_transfer(
                    transfer_id=transfer_id, receiving_manager=request.user,
                    quantity=int(request.POST.get('quantity', '0')),
                    note=request.POST.get('note', ''),
                )
            elif self.action == 'reject':
                transfer = TransferService.reject_transfer(
                    transfer_id=transfer_id, rejecting_manager=request.user,
                    reason=request.POST.get('reason', ''),
                )
            elif self.action == 'cancel':
                transfer = TransferService.cancel_transfer(
                    transfer_id=transfer_id, cancelling_manager=request.user,
                    reason=request.POST.get('reason', ''),
                )
            else:
                raise Http404()
        except (ValidationError, ValueError, TransferRequest.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'Transfer #{transfer.pk} is now {transfer.get_status_display()}.')
        return _workspace_redirect(branch)


class TransferApproveWorkspaceView(TransferActionWorkspaceView):
    action = 'approve'


class TransferDispatchWorkspaceView(TransferActionWorkspaceView):
    action = 'dispatch'


class TransferReceiveWorkspaceView(TransferActionWorkspaceView):
    action = 'receive'


class TransferRejectWorkspaceView(TransferActionWorkspaceView):
    action = 'reject'


class TransferCancelWorkspaceView(TransferActionWorkspaceView):
    action = 'cancel'


class ManualAdjustmentWorkspaceView(InventoryWorkspaceAccessMixin, View):
    def post(self, request):
        branch = _selected_branch(request)
        try:
            product, variant = _resolve_item(request.POST.get('item'))
            stock, _, created = InventoryOperationsService.record_manual_adjustment(
                branch=branch, actor=request.user,
                change_amount=int(request.POST.get('change_amount', '0')),
                reason=request.POST.get('reason', ''),
                reference_number=request.POST.get('reference_number', ''),
                note=request.POST.get('note', ''),
                product=product, variant=variant,
            )
        except (ValidationError, ValueError, Product.DoesNotExist, ProductVariant.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(
                request,
                f"Adjustment {'recorded' if created else 'already recorded'}; sellable quantity is {stock.quantity}.",
            )
        return _workspace_redirect(branch)


class StockCountStartWorkspaceView(InventoryWorkspaceAccessMixin, View):
    def post(self, request):
        branch = _selected_branch(request)
        try:
            count = InventoryOperationsService.start_count(
                branch=branch, actor=request.user, notes=request.POST.get('notes', ''),
            )
        except ValidationError as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'Stock count #{count.pk} started.')
        return _workspace_redirect(branch)


class StockCountCompleteWorkspaceView(InventoryWorkspaceAccessMixin, View):
    def post(self, request, stock_count_id):
        branch = _selected_branch(request)
        try:
            count = StockCount.objects.get(pk=stock_count_id)
            for line in count.lines.order_by('pk'):
                InventoryOperationsService.record_counted_quantity(
                    stock_count_id=count.pk, line_id=line.pk, actor=request.user,
                    quantity=int(request.POST.get(f'line_{line.pk}', '-1')),
                )
            InventoryOperationsService.complete_count(
                stock_count_id=count.pk, actor=request.user,
            )
        except (ValidationError, ValueError, StockCount.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'Stock count #{count.pk} completed.')
        return _workspace_redirect(branch)


class StockCountCancelWorkspaceView(InventoryWorkspaceAccessMixin, View):
    def post(self, request, stock_count_id):
        branch = _selected_branch(request)
        try:
            count = InventoryOperationsService.cancel_count(
                stock_count_id=stock_count_id, actor=request.user,
                reason=request.POST.get('reason', ''),
            )
        except (ValidationError, StockCount.DoesNotExist) as exc:
            messages.error(request, _message(exc))
        else:
            messages.success(request, f'Stock count #{count.pk} cancelled.')
        return _workspace_redirect(branch)
