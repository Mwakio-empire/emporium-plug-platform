from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Stock, TransferReceipt, TransferRequest
from .services import InventoryService


class TransferService:
    """Validated request-to-receipt workflow for physical branch transfers."""

    MANAGER_ROLES = ('INVENTORY_MANAGER', 'BRANCH_MANAGER', 'SUPER_ADMIN')

    @staticmethod
    def _assert_manager(user, branch_id, role_error, branch_error):
        if user.role not in TransferService.MANAGER_ROLES:
            raise ValidationError(role_error)
        if user.role != 'SUPER_ADMIN' and user.branch_id != branch_id:
            raise ValidationError(branch_error)

    @staticmethod
    def _assert_manager_for_either_branch(user, from_branch_id, to_branch_id):
        if user.role not in TransferService.MANAGER_ROLES:
            raise ValidationError(
                "Only inventory managers, branch managers or super admins can request transfers."
            )
        if user.role != 'SUPER_ADMIN' and user.branch_id not in {from_branch_id, to_branch_id}:
            raise ValidationError("You can only request a transfer involving your own branch.")

    @staticmethod
    @transaction.atomic
    def request_transfer(*, requesting_manager, from_branch, to_branch, quantity,
                         product=None, variant=None, notes=''):
        if from_branch.pk == to_branch.pk:
            raise ValidationError("Cannot transfer stock to the same branch.")
        if not from_branch.is_active or not to_branch.is_active:
            raise ValidationError("Both transfer branches must be active.")
        if int(quantity) <= 0:
            raise ValidationError("Transfer quantity must be greater than zero.")
        if bool(product) == bool(variant):
            raise ValidationError("Provide exactly one of product or variant.")

        TransferService._assert_manager_for_either_branch(
            requesting_manager, from_branch.pk, to_branch.pk,
        )

        lookup = (
            {'variant': variant, 'branch': from_branch}
            if variant else {'product': product, 'branch': from_branch}
        )
        stock = Stock.objects.filter(**lookup).first()
        available = stock.available_quantity if stock else 0
        if int(quantity) > available:
            item_name = str(variant) if variant else str(product)
            raise ValidationError(
                f"Insufficient stock: '{item_name}' has {available} unit(s) at {from_branch.name}."
            )

        transfer = TransferRequest.objects.create(
            product=product, variant=variant, quantity=int(quantity),
            from_branch=from_branch, to_branch=to_branch,
            requested_by=requesting_manager, notes=notes.strip(),
            status=TransferRequest.Status.REQUESTED,
        )
        transfer_id = str(transfer.pk)
        transaction.on_commit(lambda: TransferService._notify_request(transfer_id))
        return transfer

    @staticmethod
    @transaction.atomic
    def approve_transfer(*, transfer_id, approving_manager):
        transfer = TransferRequest.objects.select_for_update().select_related(
            'from_branch', 'to_branch', 'product', 'variant',
        ).get(pk=transfer_id)
        if transfer.status != TransferRequest.Status.REQUESTED:
            raise ValidationError(f"Transfer cannot be approved from {transfer.get_status_display()}.")
        TransferService._assert_manager(
            approving_manager, transfer.from_branch_id,
            "Only branch managers or super admins can approve transfers.",
            "You can only approve transfers leaving your own branch.",
        )
        transfer.status = TransferRequest.Status.APPROVED
        transfer.approved_by = approving_manager
        transfer.approved_at = timezone.now()
        transfer.save(update_fields=['status', 'approved_by', 'approved_at'])
        return transfer

    @staticmethod
    @transaction.atomic
    def dispatch_transfer(*, transfer_id, dispatching_manager):
        transfer = TransferRequest.objects.select_for_update().select_related(
            'product', 'variant', 'from_branch', 'to_branch',
        ).get(pk=transfer_id)
        if transfer.status != TransferRequest.Status.APPROVED:
            raise ValidationError(
                f"Transfer must be approved before dispatch. Current state: {transfer.get_status_display()}."
            )
        TransferService._assert_manager(
            dispatching_manager, transfer.from_branch_id,
            "Only branch managers or super admins can dispatch transfers.",
            "You can only dispatch transfers from your own branch.",
        )
        ref = f"TRF-{transfer.pk}"
        InventoryService.dispatch_transfer(
            branch=transfer.from_branch, quantity=transfer.quantity,
            triggered_by=dispatching_manager,
            variant=transfer.variant, product=transfer.product,
            reference_number=ref,
            note=f"Dispatched to {transfer.to_branch.name}.",
        )
        transfer.status = TransferRequest.Status.DISPATCHED
        transfer.dispatched_by = dispatching_manager
        transfer.dispatched_at = timezone.now()
        transfer.save(update_fields=['status', 'dispatched_by', 'dispatched_at'])
        transfer_id_str = str(transfer.pk)
        transaction.on_commit(lambda: TransferService._notify_request(transfer_id_str))
        return transfer

    @staticmethod
    @transaction.atomic
    def receive_transfer(*, transfer_id, receiving_manager, quantity, note=''):
        transfer = TransferRequest.objects.select_for_update().select_related(
            'product', 'variant', 'from_branch', 'to_branch',
        ).get(pk=transfer_id)
        if transfer.status not in {
            TransferRequest.Status.DISPATCHED,
            TransferRequest.Status.PARTIALLY_RECEIVED,
        }:
            raise ValidationError(
                f"Transfer is not available for receipt. Current state: {transfer.get_status_display()}."
            )
        TransferService._assert_manager(
            receiving_manager, transfer.to_branch_id,
            "Only branch managers or super admins can receive transfers.",
            "You can only receive transfers arriving at your own branch.",
        )
        quantity = int(quantity)
        if quantity <= 0 or quantity > transfer.remaining_quantity:
            raise ValidationError(
                f"Receipt quantity must be between 1 and {transfer.remaining_quantity}."
            )

        receipt = TransferReceipt.objects.create(
            transfer=transfer, quantity=quantity,
            received_by=receiving_manager, note=note.strip(),
        )
        InventoryService.receive_transfer(
            from_branch=transfer.from_branch,
            to_branch=transfer.to_branch,
            quantity=quantity,
            triggered_by=receiving_manager,
            variant=transfer.variant, product=transfer.product,
            reference_number=f"TRF-{transfer.pk}-RCV-{receipt.pk}",
            note=note.strip() or f"Received from {transfer.from_branch.name}.",
        )

        transfer.received_quantity += quantity
        transfer.confirmed_by = receiving_manager
        transfer.confirmed_at = timezone.now()
        if transfer.received_quantity == transfer.quantity:
            transfer.status = TransferRequest.Status.RECEIVED
        else:
            transfer.status = TransferRequest.Status.PARTIALLY_RECEIVED
        transfer.save(update_fields=[
            'received_quantity', 'status', 'confirmed_by', 'confirmed_at',
        ])
        transfer_id_str = str(transfer.pk)
        transaction.on_commit(lambda: TransferService._notify_confirmed(transfer_id_str))
        return transfer, receipt

    @staticmethod
    def confirm_transfer(*, transfer_id, confirming_manager):
        """Compatibility wrapper that receives the entire outstanding balance."""
        transfer = TransferRequest.objects.get(pk=transfer_id)
        transfer, _ = TransferService.receive_transfer(
            transfer_id=transfer_id,
            receiving_manager=confirming_manager,
            quantity=transfer.remaining_quantity,
        )
        return transfer

    @staticmethod
    @transaction.atomic
    def reject_transfer(*, transfer_id, rejecting_manager, reason):
        reason = reason.strip() if reason else ''
        if not reason:
            raise ValidationError("A rejection reason is mandatory.")
        transfer = TransferRequest.objects.select_for_update().get(pk=transfer_id)
        if transfer.status != TransferRequest.Status.REQUESTED:
            raise ValidationError(f"Transfer cannot be rejected from {transfer.get_status_display()}.")
        TransferService._assert_manager(
            rejecting_manager, transfer.from_branch_id,
            "Only branch managers or super admins can reject transfers.",
            "You can only reject a request against your own branch stock.",
        )
        transfer.status = TransferRequest.Status.REJECTED
        transfer.confirmed_by = rejecting_manager
        transfer.confirmed_at = timezone.now()
        transfer.rejection_reason = reason
        transfer.save(update_fields=[
            'status', 'confirmed_by', 'confirmed_at', 'rejection_reason',
        ])
        return transfer

    @staticmethod
    @transaction.atomic
    def cancel_transfer(*, transfer_id, cancelling_manager, reason):
        reason = reason.strip() if reason else ''
        if not reason:
            raise ValidationError("A cancellation reason is mandatory.")
        transfer = TransferRequest.objects.select_for_update().get(pk=transfer_id)
        if transfer.status not in {
            TransferRequest.Status.REQUESTED,
            TransferRequest.Status.APPROVED,
        }:
            raise ValidationError("A dispatched or completed transfer cannot be cancelled.")
        TransferService._assert_manager_for_either_branch(
            cancelling_manager, transfer.from_branch_id, transfer.to_branch_id,
        )
        transfer.status = TransferRequest.Status.CANCELLED
        transfer.cancelled_by = cancelling_manager
        transfer.cancelled_at = timezone.now()
        transfer.cancellation_reason = reason
        transfer.save(update_fields=[
            'status', 'cancelled_by', 'cancelled_at', 'cancellation_reason',
        ])
        return transfer

    @staticmethod
    def _notify_request(transfer_id):
        from notifications.tasks import send_transfer_request_alert
        send_transfer_request_alert.delay(transfer_id)

    @staticmethod
    def _notify_confirmed(transfer_id):
        from notifications.tasks import send_transfer_confirmed_alert
        send_transfer_confirmed_alert.delay(transfer_id)
