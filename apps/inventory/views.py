from django.core.exceptions import ValidationError
from django.db import models
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from branches.models import Branch
from catalog.models import Product, ProductVariant
from users.models import User
from users.permissions import IsInventoryController

from .intake_services import SupplierIntakeService
from .models import StockCount, StockCountLine, StockIntake, TransferRequest
from .operation_services import InventoryOperationsService
from .serializers import (
    ManualStockAdjustmentSerializer,
    StockCountCreateSerializer,
    StockCountQuantitySerializer,
    StockCountSerializer,
    StockIntakeCreateSerializer,
    StockIntakeSerializer,
    TransferReceiptCreateSerializer,
    TransferRequestCreateSerializer,
    TransferRequestSerializer,
)
from .transfer_services import TransferService


def _error_message(exc):
    return exc.message if hasattr(exc, 'message') else exc.messages[0]


class TransferRequestListCreateView(generics.ListAPIView):
    serializer_class = TransferRequestSerializer
    permission_classes = [IsInventoryController]

    def get_queryset(self):
        user = self.request.user
        qs = TransferRequest.objects.select_related(
            'product', 'variant', 'from_branch', 'to_branch', 'requested_by',
        ).prefetch_related('receipts__received_by')
        if user.role == User.Role.SUPER_ADMIN:
            return qs
        return qs.filter(models.Q(from_branch=user.branch) | models.Q(to_branch=user.branch))

    def post(self, request, *args, **kwargs):
        serializer = TransferRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            to_branch = Branch.objects.get(pk=data['to_branch_id'], is_active=True)
            if data.get('from_branch_id'):
                from_branch = Branch.objects.get(
                    pk=data['from_branch_id'], is_active=True,
                )
            elif request.user.role != User.Role.SUPER_ADMIN and request.user.branch_id:
                from_branch = request.user.branch
            else:
                return Response(
                    {'error': 'from_branch_id is required.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Branch.DoesNotExist:
            return Response(
                {'error': 'An active transfer branch was not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if data.get('product_id'):
                product = Product.objects.get(pk=data['product_id'])
                variant = None
            else:
                product = None
                variant = ProductVariant.objects.select_related('product').get(
                    pk=data['variant_id'],
                )
        except (Product.DoesNotExist, ProductVariant.DoesNotExist):
            return Response(
                {'error': 'The requested catalog item was not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            transfer = TransferService.request_transfer(
                requesting_manager=request.user,
                from_branch=from_branch,
                to_branch=to_branch,
                quantity=data['quantity'], product=product, variant=variant,
                notes=data.get('notes', ''),
            )
        except ValidationError as exc:
            return Response(
                {'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            TransferRequestSerializer(transfer).data,
            status=status.HTTP_201_CREATED,
        )


class TransferActionView(APIView):
    permission_classes = [IsInventoryController]
    service_method = None
    actor_argument = None

    def post(self, request, transfer_id):
        try:
            transfer = self.service_method(
                transfer_id=transfer_id,
                **{self.actor_argument: request.user},
            )
        except TransferRequest.DoesNotExist:
            return Response({'error': 'Transfer not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransferRequestSerializer(transfer).data)


class TransferApproveView(TransferActionView):
    service_method = staticmethod(TransferService.approve_transfer)
    actor_argument = 'approving_manager'


class TransferDispatchView(TransferActionView):
    service_method = staticmethod(TransferService.dispatch_transfer)
    actor_argument = 'dispatching_manager'


class TransferConfirmView(TransferActionView):
    service_method = staticmethod(TransferService.confirm_transfer)
    actor_argument = 'confirming_manager'


class TransferReceiveView(APIView):
    permission_classes = [IsInventoryController]

    def post(self, request, transfer_id):
        serializer = TransferReceiptCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transfer, _ = TransferService.receive_transfer(
                transfer_id=transfer_id,
                receiving_manager=request.user,
                quantity=serializer.validated_data['quantity'],
                note=serializer.validated_data.get('note', ''),
            )
        except TransferRequest.DoesNotExist:
            return Response({'error': 'Transfer not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransferRequestSerializer(transfer).data)


class TransferRejectView(APIView):
    permission_classes = [IsInventoryController]

    def post(self, request, transfer_id):
        try:
            transfer = TransferService.reject_transfer(
                transfer_id=transfer_id, rejecting_manager=request.user,
                reason=request.data.get('reason', ''),
            )
        except TransferRequest.DoesNotExist:
            return Response({'error': 'Transfer not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransferRequestSerializer(transfer).data)


class TransferCancelView(APIView):
    permission_classes = [IsInventoryController]

    def post(self, request, transfer_id):
        try:
            transfer = TransferService.cancel_transfer(
                transfer_id=transfer_id, cancelling_manager=request.user,
                reason=request.data.get('reason', ''),
            )
        except TransferRequest.DoesNotExist:
            return Response({'error': 'Transfer not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransferRequestSerializer(transfer).data)


class StockIntakeListCreateView(generics.ListAPIView):
    serializer_class = StockIntakeSerializer
    permission_classes = [IsInventoryController]

    def get_queryset(self):
        qs = StockIntake.objects.select_related(
            'branch', 'received_by',
        ).prefetch_related('lines__product', 'lines__variant')
        if self.request.user.role == User.Role.SUPER_ADMIN:
            return qs
        return qs.filter(branch=self.request.user.branch)

    def post(self, request, *args, **kwargs):
        serializer = StockIntakeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch_id = data.get('branch_id') or request.user.branch_id
        if not branch_id:
            return Response(
                {'error': 'branch_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            branch = Branch.objects.get(pk=branch_id)
        except Branch.DoesNotExist:
            return Response({'error': 'Branch not found.'}, status=status.HTTP_400_BAD_REQUEST)

        lines = []
        try:
            for line in data['lines']:
                if line.get('product_id'):
                    product = Product.objects.get(pk=line['product_id'])
                    variant = None
                else:
                    product = None
                    variant = ProductVariant.objects.select_related('product').get(
                        pk=line['variant_id'],
                    )
                lines.append({
                    'product': product, 'variant': variant,
                    'quantity': line['quantity'],
                })
        except (Product.DoesNotExist, ProductVariant.DoesNotExist):
            return Response(
                {'error': 'An intake catalog item was not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            intake, created = SupplierIntakeService.record_intake(
                branch=branch,
                supplier_name=data['supplier_name'],
                delivery_reference=data['delivery_reference'],
                received_by=request.user,
                lines=lines,
                notes=data.get('notes', ''),
            )
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            StockIntakeSerializer(intake).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ManualStockAdjustmentView(APIView):
    permission_classes = [IsInventoryController]

    def post(self, request):
        serializer = ManualStockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch_id = data.get('branch_id') or request.user.branch_id
        try:
            branch = Branch.objects.get(pk=branch_id)
            if data.get('product_id'):
                product = Product.objects.get(pk=data['product_id'])
                variant = None
            else:
                product = None
                variant = ProductVariant.objects.get(pk=data['variant_id'])
        except (Branch.DoesNotExist, Product.DoesNotExist, ProductVariant.DoesNotExist):
            return Response(
                {'error': 'The branch or catalog item was not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            stock, audit, created = InventoryOperationsService.record_manual_adjustment(
                branch=branch, actor=request.user,
                change_amount=data['change_amount'], reason=data['reason'],
                reference_number=data['reference_number'], note=data['note'],
                product=product, variant=variant,
            )
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'created': created,
            'stock_id': stock.pk,
            'quantity': stock.quantity,
            'damaged_quantity': stock.damaged_quantity,
            'audit_id': audit.pk,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class StockCountListCreateView(generics.ListAPIView):
    serializer_class = StockCountSerializer
    permission_classes = [IsInventoryController]

    def get_queryset(self):
        qs = StockCount.objects.select_related('branch').prefetch_related(
            'lines__product', 'lines__variant',
        )
        if self.request.user.role == User.Role.SUPER_ADMIN:
            return qs
        return qs.filter(branch=self.request.user.branch)

    def post(self, request, *args, **kwargs):
        serializer = StockCountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch_id = data.get('branch_id') or request.user.branch_id
        try:
            branch = Branch.objects.get(pk=branch_id)
            count = InventoryOperationsService.start_count(
                branch=branch, actor=request.user,
                stock_ids=data.get('stock_ids'), notes=data.get('notes', ''),
            )
        except Branch.DoesNotExist:
            return Response({'error': 'Branch not found.'}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockCountSerializer(count).data, status=status.HTTP_201_CREATED)


class StockCountLineUpdateView(APIView):
    permission_classes = [IsInventoryController]

    def post(self, request, stock_count_id, line_id):
        serializer = StockCountQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            line = InventoryOperationsService.record_counted_quantity(
                stock_count_id=stock_count_id, line_id=line_id,
                actor=request.user,
                quantity=serializer.validated_data['counted_quantity'],
            )
        except (StockCount.DoesNotExist, StockCountLine.DoesNotExist):
            return Response({'error': 'Stock count line not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'line_id': line.pk, 'counted_quantity': line.counted_quantity})


class StockCountCompleteView(APIView):
    permission_classes = [IsInventoryController]

    def post(self, request, stock_count_id):
        try:
            count = InventoryOperationsService.complete_count(
                stock_count_id=stock_count_id, actor=request.user,
            )
        except StockCount.DoesNotExist:
            return Response({'error': 'Stock count not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockCountSerializer(count).data)


class StockCountCancelView(APIView):
    permission_classes = [IsInventoryController]

    def post(self, request, stock_count_id):
        try:
            count = InventoryOperationsService.cancel_count(
                stock_count_id=stock_count_id, actor=request.user,
                reason=request.data.get('reason', ''),
            )
        except StockCount.DoesNotExist:
            return Response({'error': 'Stock count not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response({'error': _error_message(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockCountSerializer(count).data)
