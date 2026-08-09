from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from rest_framework.test import APIClient

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import (
    LowStockAlertState, Stock, StockAuditLog, StockCount, TransferRequest,
)
from inventory.operation_services import InventoryOperationsService
from inventory.services import InventoryService
from inventory.transfer_services import TransferService


User = get_user_model()


class AtomicInventoryCatalogEngineTestCase(TestCase):

    def setUp(self):
        # Create Branch Architecture context
        self.branch = Branch.objects.create(name="Nairobi West", location="Langata Road")
        
        # Create RBAC authorized profile context
        self.inventory_manager = User.objects.create_user(
            username="stock_guru",
            phone_number="+254700000001",
            role=User.Role.INVENTORY_MANAGER,
            branch=self.branch,
        )
        
        # Build nested hierarchical category environment 
        self.root_cat = Category.objects.create(name="Electronics", slug="electronics")
        self.sub_cat = Category.objects.create(name="Smartphones", parent=self.root_cat, slug="smartphones")

        # Build primary product item 
        self.product = Product.objects.create(
            name="iPhone 15 Pro",
            category=self.sub_cat,
            price=150000.00,
            low_stock_threshold=3
        )

        # Generate individual variant sub-item trackings
        self.variant_blue = ProductVariant.objects.create(
            product=self.product,
            attribute_name="Color",
            attribute_value="Titanium Blue"
        )

    def test_nested_category_string_representation(self):
        """Validates that nested categories generate correct string breadcrumbs."""
        self.assertEqual(str(self.sub_cat), "Electronics > Smartphones")

    def test_automatic_sku_generation_protocol(self):
        """Guarantees unique SKUs auto-populate using category prefixes upon save actions."""
        self.assertTrue(self.product.sku.startswith("SMA-"))

    def test_atomic_restock_service_flow(self):
        """Validates that a positive inventory adjustment updates balances and logs clean audit fields."""
        stock, audit = InventoryService.adjust_stock(
            variant=self.variant_blue,
            branch=self.branch,
            change_amount=10,
            reason=StockAuditLog.Reason.RESTOCK,
            triggered_by=self.inventory_manager
        )
        
        self.assertEqual(stock.quantity, 10)
        self.assertEqual(audit.running_total, 10)
        self.assertEqual(audit.change_amount, 10)
        self.assertEqual(audit.reason, StockAuditLog.Reason.RESTOCK)

    def test_overselling_race_condition_prevention_logic(self):
        """Ensures that validation errors throw immediately if transactions attempt to drive stock negative."""
        # Baseline restock initialization setup
        InventoryService.adjust_stock(
            variant=self.variant_blue,
            branch=self.branch,
            change_amount=5,
            reason=StockAuditLog.Reason.RESTOCK,
            triggered_by=self.inventory_manager
        )

        # Attempting to deduct more than the current stock levels must raise a ValidationError
        with self.assertRaises(ValidationError):
            InventoryService.adjust_stock(
                variant=self.variant_blue,
                branch=self.branch,
                change_amount=-10,  # Exceeds current stock levels
                reason=StockAuditLog.Reason.SALE,
                triggered_by=self.inventory_manager
            )

        # Re-verify database layer was rolled back safely and stock remains unchanged
        current_stock = Stock.objects.get(variant=self.variant_blue, branch=self.branch)
        self.assertEqual(current_stock.quantity, 5)



class InterBranchTransferTestCase(TestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(name="Transfer Test Branch A", location="A")
        self.branch_b = Branch.objects.create(name="Transfer Test Branch B", location="B")
        self.branch_c = Branch.objects.create(name="Transfer Test Branch C", location="C")

        self.manager_a = User.objects.create_user(
            username="transfer_manager_a", phone_number="+254733600001",
            email="transfer.manager.a@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch_a,
        )
        self.manager_a2 = User.objects.create_user(
            username="transfer_manager_a2", phone_number="+254733600002",
            email="transfer.manager.a2@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch_a,
        )
        self.manager_b = User.objects.create_user(
            username="transfer_manager_b", phone_number="+254733600003",
            email="transfer.manager.b@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch_b,
        )
        self.manager_b2 = User.objects.create_user(
            username="transfer_manager_b2", phone_number="+254733600004",
            email="transfer.manager.b2@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch_b,
        )
        self.manager_c = User.objects.create_user(
            username="transfer_manager_c", phone_number="+254733600005",
            email="transfer.manager.c@test.ke", password="ManagerPass123!",
            role=User.Role.BRANCH_MANAGER, branch=self.branch_c,
        )
        self.staff_a = User.objects.create_user(
            username="transfer_staff_a", phone_number="+254733600006",
            email="transfer.staff.a@test.ke", password="StaffPass123!",
            role=User.Role.STAFF, branch=self.branch_a,
        )
        self.super_admin = User.objects.create_user(
            username="transfer_superadmin", phone_number="+254733600007",
            email="transfer.superadmin@test.ke", password="SuperAdminPass123!",
            role=User.Role.SUPER_ADMIN, is_staff=True, is_superuser=True,
        )

        self.category = Category.objects.create(name="Transfer Test Category", slug="transfer-test-category")
        self.product = Product.objects.create(
            name="Transfer Test Product", category=self.category, slug="transfer-test-product", price=Decimal("1000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, attribute_name="Unit", attribute_value="Single",
        )
        self.stock_a = Stock.objects.create(branch=self.branch_a, variant=self.variant, quantity=50)
        self.stock_b = Stock.objects.create(branch=self.branch_b, variant=self.variant, quantity=10)

    def _approve(self, transfer):
        return TransferService.approve_transfer(
            transfer_id=transfer.pk, approving_manager=self.manager_a,
        )

    def test_transfer_stock_rows_are_locked_in_stable_branch_order(self):
        locked = {
            self.branch_a.pk: self.stock_a,
            self.branch_b.pk: self.stock_b,
        }
        calls = []

        def record_lock(*, branch, variant=None, product=None):
            calls.append(branch.pk)
            return locked[branch.pk]

        with patch.object(InventoryService, '_locked_stock', side_effect=record_lock):
            source, destination = InventoryService._lock_transfer_stocks(
                from_branch=self.branch_b,
                to_branch=self.branch_a,
                variant=self.variant,
            )

        self.assertEqual(calls, sorted((self.branch_a.pk, self.branch_b.pk)))
        self.assertEqual(source.pk, self.stock_b.pk)
        self.assertEqual(destination.pk, self.stock_a.pk)

    # --- request_transfer guards ---

    def test_same_branch_transfer_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            TransferService.request_transfer(
                requesting_manager=self.manager_a, from_branch=self.branch_a,
                to_branch=self.branch_a, quantity=5, variant=self.variant,
            )
        self.assertIn("same branch", str(ctx.exception))

    def test_zero_quantity_rejected(self):
        with self.assertRaises(ValidationError):
            TransferService.request_transfer(
                requesting_manager=self.manager_a, from_branch=self.branch_a,
                to_branch=self.branch_b, quantity=0, variant=self.variant,
            )

    def test_both_product_and_variant_rejected(self):
        with self.assertRaises(ValidationError):
            TransferService.request_transfer(
                requesting_manager=self.manager_a, from_branch=self.branch_a,
                to_branch=self.branch_b, quantity=5,
                product=self.product, variant=self.variant,
            )

    def test_neither_product_nor_variant_rejected(self):
        with self.assertRaises(ValidationError):
            TransferService.request_transfer(
                requesting_manager=self.manager_a, from_branch=self.branch_a,
                to_branch=self.branch_b, quantity=5,
            )

    def test_staff_cannot_request_transfer(self):
        with self.assertRaises(ValidationError) as ctx:
            TransferService.request_transfer(
                requesting_manager=self.staff_a, from_branch=self.branch_a,
                to_branch=self.branch_b, quantity=5, variant=self.variant,
            )
        self.assertIn("inventory managers", str(ctx.exception))

    def test_manager_cannot_request_transfer_from_other_branch(self):
        """manager_b (assigned to branch_b) cannot request a transfer OUT of branch_a."""
        with self.assertRaises(ValidationError) as ctx:
            TransferService.request_transfer(
                requesting_manager=self.manager_b, from_branch=self.branch_a,
                to_branch=self.branch_c, quantity=5, variant=self.variant,
            )
        self.assertIn("own branch", str(ctx.exception))

    def test_insufficient_stock_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            TransferService.request_transfer(
                requesting_manager=self.manager_a, from_branch=self.branch_a,
                to_branch=self.branch_b, quantity=999, variant=self.variant,
            )
        self.assertIn("Insufficient stock", str(ctx.exception))
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 50)  # untouched

    def test_super_admin_can_request_cross_branch_transfer(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.super_admin, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        self.assertEqual(transfer.status, TransferRequest.Status.REQUESTED)
        self.assertEqual(transfer.requested_by, self.super_admin)

    def test_successful_request_does_not_touch_stock_yet(self):
        TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 50)
        self.assertEqual(self.stock_b.quantity, 10)

    # --- confirm_transfer guards ---

    def test_manager_cannot_dispatch_from_another_branch(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        self._approve(transfer)
        with self.assertRaises(ValidationError):
            TransferService.dispatch_transfer(
                transfer_id=transfer.id,
                dispatching_manager=self.manager_b,
            )
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TransferRequest.Status.APPROVED)

    def test_destination_requester_can_receive_after_source_approval(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_b, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(
            transfer_id=transfer.id, dispatching_manager=self.manager_a,
        )
        confirmed = TransferService.confirm_transfer(
            transfer_id=transfer.id, confirming_manager=self.manager_b,
        )
        self.assertEqual(confirmed.status, TransferRequest.Status.RECEIVED)
    def test_wrong_branch_manager_cannot_confirm(self):
        """manager_c (branch_c) cannot confirm a transfer arriving at branch_b."""
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        with self.assertRaises(ValidationError) as ctx:
            TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_c)
        self.assertIn("own branch", str(ctx.exception))

    def test_staff_cannot_confirm_transfer(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        staff_b = User.objects.create_user(
            username="transfer_staff_b", phone_number="+254733600008",
            email="transfer.staff.b@test.ke", password="StaffPass123!",
            role=User.Role.STAFF, branch=self.branch_b,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        with self.assertRaises(ValidationError):
            TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=staff_b)

    def test_already_confirmed_transfer_cannot_be_reconfirmed(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_b)
        with self.assertRaises(ValidationError) as ctx:
            TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_b2)
        self.assertIn("not available", str(ctx.exception))

    # --- successful confirm: stock + audit log correctness ---

    def test_successful_confirm_moves_stock_correctly(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=7, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 43)
        self.assertEqual(self.stock_a.in_transit_quantity, 7)
        self.assertEqual(self.stock_b.quantity, 10)
        confirmed = TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_b)

        self.assertEqual(confirmed.status, TransferRequest.Status.RECEIVED)
        self.assertEqual(confirmed.confirmed_by, self.manager_b)
        self.assertIsNotNone(confirmed.confirmed_at)

        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 43)  # 50 - 7
        self.assertEqual(self.stock_a.in_transit_quantity, 0)
        self.assertEqual(self.stock_b.quantity, 17)  # 10 + 7

    def test_successful_confirm_writes_both_audit_log_entries(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=3, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_b)

        ref = f"TRF-{transfer.id}"
        out_log = StockAuditLog.objects.get(reference_number=ref, reason=StockAuditLog.Reason.TRANSFER_OUT)
        in_log = StockAuditLog.objects.get(
            reference_number__startswith=f"{ref}-RCV-",
            reason=StockAuditLog.Reason.TRANSFER_IN,
        )

        self.assertEqual(out_log.branch, self.branch_a)
        self.assertEqual(out_log.change_amount, -3)
        self.assertEqual(out_log.running_total, 47)
        self.assertEqual(out_log.triggered_by, self.manager_a)

        self.assertEqual(in_log.branch, self.branch_b)
        self.assertEqual(in_log.change_amount, 3)
        self.assertEqual(in_log.running_total, 13)
        self.assertEqual(in_log.triggered_by, self.manager_b)

    def test_confirm_by_second_manager_on_same_receiving_branch_succeeds(self):
        """Any manager at the receiving branch (not just one specific person) can confirm."""
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=2, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        confirmed = TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_b2)
        self.assertEqual(confirmed.status, TransferRequest.Status.RECEIVED)

    def test_super_admin_can_confirm_any_branch(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=2, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        confirmed = TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.super_admin)
        self.assertEqual(confirmed.status, TransferRequest.Status.RECEIVED)

    def test_overselling_at_confirm_time_blocked(self):
        """
        Stock at from_branch drops below requested qty between request and
        confirm (e.g. a sale happened in between) -- InventoryService's own
        select_for_update + negative-stock guard must reject the transfer.
        """
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=40, variant=self.variant,
        )
        self._approve(transfer)
        # Simulate stock consumed elsewhere after the request was made
        self.stock_a.quantity = 5
        self.stock_a.save(update_fields=['quantity'])

        with self.assertRaises(ValidationError):
            TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TransferRequest.Status.APPROVED)

    # --- reject_transfer ---

    def test_reject_without_reason_rejected(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        with self.assertRaises(ValidationError) as ctx:
            TransferService.reject_transfer(transfer_id=transfer.id, rejecting_manager=self.manager_a, reason='   ')
        self.assertIn("mandatory", str(ctx.exception))

    def test_successful_rejection_leaves_stock_untouched(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        rejected = TransferService.reject_transfer(
            transfer_id=transfer.id, rejecting_manager=self.manager_a, reason="Wrong item requested",
        )
        self.assertEqual(rejected.status, TransferRequest.Status.REJECTED)
        self.assertEqual(rejected.rejection_reason, "Wrong item requested")
        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 50)
        self.assertEqual(self.stock_b.quantity, 10)

    def test_wrong_branch_manager_cannot_reject(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        with self.assertRaises(ValidationError):
            TransferService.reject_transfer(transfer_id=transfer.id, rejecting_manager=self.manager_c, reason="No.")

    def test_already_rejected_transfer_cannot_be_confirmed(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        TransferService.reject_transfer(transfer_id=transfer.id, rejecting_manager=self.manager_a, reason="No.")
        with self.assertRaises(ValidationError):
            TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_b2)

    # --- simple-product (non-variant) transfer path ---
    def test_simple_product_transfer_full_cycle(self):
        simple_product = Product.objects.create(
            name="Transfer Simple Product", slug="transfer-simple-product",
            category=self.category, price=Decimal("500.00"),
        )
        Stock.objects.create(branch=self.branch_a, product=simple_product, quantity=20)
        Stock.objects.create(branch=self.branch_b, product=simple_product, quantity=0)

        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_a, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=8, product=simple_product,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(transfer_id=transfer.id, dispatching_manager=self.manager_a)
        TransferService.confirm_transfer(transfer_id=transfer.id, confirming_manager=self.manager_b)

        self.assertEqual(
            Stock.objects.get(branch=self.branch_a, product=simple_product).quantity, 12,
        )
        self.assertEqual(
            Stock.objects.get(branch=self.branch_b, product=simple_product).quantity, 8,
        )

    def test_dispatch_requires_source_approval(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_b, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        with self.assertRaisesMessage(ValidationError, 'approved before dispatch'):
            TransferService.dispatch_transfer(
                transfer_id=transfer.pk, dispatching_manager=self.manager_a,
            )

    def test_only_source_branch_can_approve(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_b, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        with self.assertRaisesMessage(ValidationError, 'own branch'):
            TransferService.approve_transfer(
                transfer_id=transfer.pk, approving_manager=self.manager_b,
            )

    def test_partial_receipts_preserve_in_transit_custody_and_history(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_b, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=7, variant=self.variant,
        )
        self._approve(transfer)
        TransferService.dispatch_transfer(
            transfer_id=transfer.pk, dispatching_manager=self.manager_a,
        )
        partial, first_receipt = TransferService.receive_transfer(
            transfer_id=transfer.pk, receiving_manager=self.manager_b,
            quantity=3, note='First carton received.',
        )
        self.assertEqual(partial.status, TransferRequest.Status.PARTIALLY_RECEIVED)
        self.assertEqual(partial.received_quantity, 3)
        self.assertEqual(first_receipt.quantity, 3)
        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 43)
        self.assertEqual(self.stock_a.in_transit_quantity, 4)
        self.assertEqual(self.stock_b.quantity, 13)

        completed, second_receipt = TransferService.receive_transfer(
            transfer_id=transfer.pk, receiving_manager=self.manager_b2,
            quantity=4, note='Balance received.',
        )
        self.assertEqual(completed.status, TransferRequest.Status.RECEIVED)
        self.assertEqual(completed.received_quantity, 7)
        self.assertEqual(second_receipt.quantity, 4)
        self.stock_a.refresh_from_db()
        self.stock_b.refresh_from_db()
        self.assertEqual(self.stock_a.in_transit_quantity, 0)
        self.assertEqual(self.stock_b.quantity, 17)
        self.assertEqual(completed.receipts.count(), 2)

    def test_approved_transfer_can_be_cancelled_before_dispatch(self):
        transfer = TransferService.request_transfer(
            requesting_manager=self.manager_b, from_branch=self.branch_a,
            to_branch=self.branch_b, quantity=5, variant=self.variant,
        )
        self._approve(transfer)
        cancelled = TransferService.cancel_transfer(
            transfer_id=transfer.pk, cancelling_manager=self.manager_b,
            reason='The shop no longer needs this quantity.',
        )
        self.assertEqual(cancelled.status, TransferRequest.Status.CANCELLED)
        self.stock_a.refresh_from_db()
        self.assertEqual(self.stock_a.quantity, 50)
        self.assertEqual(self.stock_a.in_transit_quantity, 0)


class SupplierIntakeTests(TestCase):
    def setUp(self):
        from inventory.intake_services import SupplierIntakeService

        self.service = SupplierIntakeService
        self.otc = Branch.objects.create(
            name='OTC Receiving Hub', location='OTC, Nairobi',
            receives_supplier_stock=True,
        )
        self.shop = Branch.objects.create(
            name='Gaborone Plaza Shop 1', location='Gaborone Plaza, Nairobi',
        )
        self.otc_manager = User.objects.create_user(
            username='otc_inventory_manager', phone_number='+254733699910',
            email='otc.inventory@test.invalid',
            role=User.Role.INVENTORY_MANAGER, branch=self.otc,
        )
        self.shop_manager = User.objects.create_user(
            username='gaborone_inventory_manager', phone_number='+254733699911',
            email='gaborone.inventory@test.invalid',
            role=User.Role.INVENTORY_MANAGER, branch=self.shop,
        )
        category = Category.objects.create(name='Wholesale Intake', slug='wholesale-intake')
        self.simple = Product.objects.create(
            name='Wholesale Soap', slug='wholesale-soap', category=category,
            price=Decimal('100.00'),
        )
        variant_product = Product.objects.create(
            name='Wholesale Shirt', slug='wholesale-shirt', category=category,
            price=Decimal('500.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=variant_product, attribute_name='Size', attribute_value='M',
        )

    def _lines(self):
        return [
            {'product': self.simple, 'quantity': 20},
            {'variant': self.variant, 'quantity': 10},
        ]

    def test_supplier_intake_is_restricted_to_configured_hub(self):
        with self.assertRaisesMessage(ValidationError, 'not configured'):
            self.service.record_intake(
                branch=self.shop, supplier_name='Supplier A',
                delivery_reference='DEL-001', received_by=self.shop_manager,
                lines=[{'product': self.simple, 'quantity': 5}],
            )

    def test_intake_adds_stock_and_audits_each_line_atomically(self):
        intake, created = self.service.record_intake(
            branch=self.otc, supplier_name='Supplier A',
            delivery_reference='DEL-001', received_by=self.otc_manager,
            lines=self._lines(), notes='Checked against delivery note.',
        )
        self.assertTrue(created)
        self.assertEqual(intake.lines.count(), 2)
        self.assertEqual(Stock.objects.get(branch=self.otc, product=self.simple).quantity, 20)
        self.assertEqual(Stock.objects.get(branch=self.otc, variant=self.variant).quantity, 10)
        self.assertEqual(StockAuditLog.objects.filter(
            branch=self.otc, reason=StockAuditLog.Reason.RESTOCK,
            reference_number__startswith=f'INTAKE-{intake.pk}-LINE-',
        ).count(), 2)

    def test_duplicate_delivery_reference_is_idempotent_only_for_same_payload(self):
        first, created = self.service.record_intake(
            branch=self.otc, supplier_name='Supplier A',
            delivery_reference='DEL-002', received_by=self.otc_manager,
            lines=self._lines(),
        )
        second, created_again = self.service.record_intake(
            branch=self.otc, supplier_name='Supplier A',
            delivery_reference='DEL-002', received_by=self.otc_manager,
            lines=self._lines(),
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Stock.objects.get(branch=self.otc, product=self.simple).quantity, 20)
        with self.assertRaisesMessage(ValidationError, 'different intake details'):
            self.service.record_intake(
                branch=self.otc, supplier_name='Supplier A',
                delivery_reference='DEL-002', received_by=self.otc_manager,
                lines=[{'product': self.simple, 'quantity': 999}],
            )

    def test_other_branch_inventory_manager_cannot_book_otc_intake(self):
        with self.assertRaisesMessage(ValidationError, 'assigned branch'):
            self.service.record_intake(
                branch=self.otc, supplier_name='Supplier A',
                delivery_reference='DEL-003', received_by=self.shop_manager,
                lines=[{'product': self.simple, 'quantity': 5}],
            )


class InventoryOperationsTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Count Branch', location='Nairobi')
        self.other = Branch.objects.create(name='Other Count Branch', location='Nairobi')
        self.manager = User.objects.create_user(
            username='count_manager', phone_number='+254733699920',
            email='count.manager@test.invalid',
            role=User.Role.INVENTORY_MANAGER, branch=self.branch,
        )
        self.other_manager = User.objects.create_user(
            username='other_count_manager', phone_number='+254733699921',
            email='other.count.manager@test.invalid',
            role=User.Role.INVENTORY_MANAGER, branch=self.other,
        )
        category = Category.objects.create(name='Count Items', slug='count-items')
        self.product = Product.objects.create(
            name='Count Product', slug='count-product', category=category,
            price=Decimal('100.00'),
        )
        self.stock = Stock.objects.create(
            branch=self.branch, product=self.product, quantity=10,
        )

    def test_damage_adjustment_is_quarantined_and_idempotent(self):
        stock, audit, created = InventoryOperationsService.record_manual_adjustment(
            branch=self.branch, actor=self.manager, product=self.product,
            change_amount=-3, reason=StockAuditLog.Reason.DAMAGE,
            reference_number='DAMAGE-001', note='Three units crushed in storage.',
        )
        self.assertTrue(created)
        self.assertEqual(stock.quantity, 7)
        self.assertEqual(stock.damaged_quantity, 3)
        same_stock, same_audit, created_again = InventoryOperationsService.record_manual_adjustment(
            branch=self.branch, actor=self.manager, product=self.product,
            change_amount=-3, reason=StockAuditLog.Reason.DAMAGE,
            reference_number='DAMAGE-001', note='Three units crushed in storage.',
        )
        self.assertFalse(created_again)
        self.assertEqual(audit.pk, same_audit.pk)
        self.assertEqual(same_stock.quantity, 7)

    def test_cross_branch_adjustment_is_denied(self):
        with self.assertRaisesMessage(ValidationError, 'assigned branch'):
            InventoryOperationsService.record_manual_adjustment(
                branch=self.branch, actor=self.other_manager, product=self.product,
                change_amount=-1, reason=StockAuditLog.Reason.THEFT,
                reference_number='THEFT-001', note='Missing after recount.',
            )

    def test_completed_stock_count_applies_audited_correction(self):
        count = InventoryOperationsService.start_count(
            branch=self.branch, actor=self.manager,
        )
        line = count.lines.get()
        InventoryOperationsService.record_counted_quantity(
            stock_count_id=count.pk, line_id=line.pk,
            actor=self.manager, quantity=8,
        )
        completed = InventoryOperationsService.complete_count(
            stock_count_id=count.pk, actor=self.manager,
        )
        self.assertEqual(completed.status, StockCount.Status.COMPLETED)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 8)
        self.assertTrue(StockAuditLog.objects.filter(
            reason=StockAuditLog.Reason.CORRECTION,
            reference_number=f'COUNT-{count.pk}-LINE-{line.pk}',
            change_amount=-2,
        ).exists())

    def test_count_restarts_if_stock_moved_after_snapshot(self):
        count = InventoryOperationsService.start_count(
            branch=self.branch, actor=self.manager,
        )
        line = count.lines.get()
        InventoryOperationsService.record_counted_quantity(
            stock_count_id=count.pk, line_id=line.pk,
            actor=self.manager, quantity=10,
        )
        InventoryService.adjust_stock(
            branch=self.branch, product=self.product, change_amount=1,
            reason=StockAuditLog.Reason.RESTOCK, triggered_by=self.manager,
            reference_number='LATE-DELIVERY',
        )
        with self.assertRaisesMessage(ValidationError, 'Stock moved'):
            InventoryOperationsService.complete_count(
                stock_count_id=count.pk, actor=self.manager,
            )

    def test_branch_cannot_have_two_open_counts(self):
        InventoryOperationsService.start_count(branch=self.branch, actor=self.manager)
        with self.assertRaisesMessage(ValidationError, 'already has an open'):
            InventoryOperationsService.start_count(branch=self.branch, actor=self.manager)


class LowStockAlertTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Low Stock Branch', location='Nairobi')
        self.manager = User.objects.create_user(
            username='low_stock_manager', phone_number='+254733699930',
            email='low.stock.manager@test.invalid',
            role=User.Role.INVENTORY_MANAGER, branch=self.branch,
        )
        category = Category.objects.create(name='Low Stock Items', slug='low-stock-items')
        self.product = Product.objects.create(
            name='Low Stock Product', slug='low-stock-product', category=category,
            price=Decimal('100.00'), low_stock_threshold=5,
        )
        self.stock = Stock.objects.create(
            branch=self.branch, product=self.product, quantity=3,
        )

    @patch('notifications.tasks.send_sms_task.delay')
    def test_alert_is_sent_on_transition_not_every_sweep(self, mock_sms):
        from inventory.tasks import send_branch_low_stock_alerts

        first = send_branch_low_stock_alerts()
        second = send_branch_low_stock_alerts()
        self.assertEqual(first['transitions'], 1)
        self.assertEqual(second['transitions'], 0)
        self.assertEqual(mock_sms.call_count, 1)
        self.assertIn('Low Stock Branch', mock_sms.call_args.args[1])
        state = LowStockAlertState.objects.get(stock=self.stock)
        self.assertTrue(state.is_active)
        self.assertIsNotNone(state.last_notified_at)

        self.stock.quantity = 10
        self.stock.save(update_fields=['quantity'])
        send_branch_low_stock_alerts()
        state.refresh_from_db()
        self.assertFalse(state.is_active)
        self.assertIsNotNone(state.resolved_at)

        self.stock.quantity = 2
        self.stock.save(update_fields=['quantity'])
        send_branch_low_stock_alerts()
        self.assertEqual(mock_sms.call_count, 2)


class Phase7InventoryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.otc = Branch.objects.create(
            name='API OTC Hub', location='OTC, Nairobi',
            receives_supplier_stock=True,
        )
        self.shop = Branch.objects.create(
            name='API Gaborone Shop', location='Gaborone Plaza, Nairobi',
        )
        self.otc_manager = User.objects.create_user(
            username='api_otc_manager', phone_number='+254733699940',
            email='api.otc.manager@test.invalid',
            role=User.Role.INVENTORY_MANAGER, branch=self.otc,
        )
        self.shop_manager = User.objects.create_user(
            username='api_shop_manager', phone_number='+254733699941',
            email='api.shop.manager@test.invalid',
            role=User.Role.INVENTORY_MANAGER, branch=self.shop,
        )
        category = Category.objects.create(name='API Wholesale', slug='api-wholesale')
        self.product = Product.objects.create(
            name='API Wholesale Product', slug='api-wholesale-product',
            category=category, price=Decimal('100.00'),
        )
        Stock.objects.create(branch=self.otc, product=self.product, quantity=20)

    def test_destination_request_to_partial_and_full_receipt_api(self):
        self.client.force_authenticate(self.shop_manager)
        response = self.client.post(reverse('inventory:transfer-list-create'), {
            'from_branch_id': self.otc.pk,
            'to_branch_id': self.shop.pk,
            'product_id': self.product.pk,
            'quantity': 10,
            'notes': 'Shop replenishment request.',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        transfer_id = response.data['id']
        self.assertEqual(response.data['status'], TransferRequest.Status.REQUESTED)

        self.client.force_authenticate(self.otc_manager)
        approved = self.client.post(reverse('inventory:transfer-approve', args=[transfer_id]))
        self.assertEqual(approved.status_code, 200)
        dispatched = self.client.post(reverse('inventory:transfer-dispatch', args=[transfer_id]))
        self.assertEqual(dispatched.status_code, 200)

        self.client.force_authenticate(self.shop_manager)
        partial = self.client.post(
            reverse('inventory:transfer-receive', args=[transfer_id]),
            {'quantity': 4, 'note': 'First parcel.'}, format='json',
        )
        self.assertEqual(partial.status_code, 200)
        self.assertEqual(partial.data['status'], TransferRequest.Status.PARTIALLY_RECEIVED)
        completed = self.client.post(
            reverse('inventory:transfer-receive', args=[transfer_id]),
            {'quantity': 6, 'note': 'Balance received.'}, format='json',
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data['status'], TransferRequest.Status.RECEIVED)
        self.assertEqual(len(completed.data['receipts']), 2)

    def test_supplier_intake_api_is_idempotent(self):
        self.client.force_authenticate(self.otc_manager)
        payload = {
            'supplier_name': 'API Supplier',
            'delivery_reference': 'API-DEL-001',
            'lines': [{'product_id': self.product.pk, 'quantity': 12}],
        }
        first = self.client.post(reverse('inventory:intake-list-create'), payload, format='json')
        second = self.client.post(reverse('inventory:intake-list-create'), payload, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(
            Stock.objects.get(branch=self.otc, product=self.product).quantity, 32,
        )


class InventoryStateMachineTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='State Branch', location='Nakuru')
        self.actor = User.objects.create_user(
            username='state_manager', phone_number='+254733699901',
            email='state.manager@example.test', password='StrongPass123!',
            role=User.Role.INVENTORY_MANAGER, branch=self.branch,
        )
        category = Category.objects.create(name='State Items', slug='state-items')
        self.product = Product.objects.create(
            name='State Product', slug='state-product', category=category,
            price=Decimal('100.00'),
        )
        self.stock = Stock.objects.create(
            branch=self.branch, product=self.product, quantity=10,
        )

    def test_reservation_changes_availability_not_physical_on_hand(self):
        InventoryService.reserve_stock(
            branch=self.branch, product=self.product, quantity=3,
            triggered_by=self.actor, reference_number='ORDER-RESERVE-1',
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 10)
        self.assertEqual(self.stock.reserved_quantity, 3)
        self.assertEqual(self.stock.available_quantity, 7)

    def test_reserved_units_are_protected_from_direct_sale_deduction(self):
        InventoryService.reserve_stock(
            branch=self.branch, product=self.product, quantity=8,
            triggered_by=self.actor, reference_number='ORDER-RESERVE-2',
        )
        with self.assertRaises(ValidationError):
            InventoryService.adjust_stock(
                branch=self.branch, product=self.product, change_amount=-3,
                reason=StockAuditLog.Reason.SALE, triggered_by=self.actor,
            )

    def test_reservation_consumption_is_idempotent(self):
        InventoryService.reserve_stock(
            branch=self.branch, product=self.product, quantity=4,
            triggered_by=self.actor, reference_number='ORDER-CONSUME-1',
        )
        InventoryService.consume_reservation(
            branch=self.branch, product=self.product, quantity=4,
            triggered_by=self.actor, reference_number='ORDER-CONSUME-1',
        )
        InventoryService.consume_reservation(
            branch=self.branch, product=self.product, quantity=4,
            triggered_by=self.actor, reference_number='ORDER-CONSUME-1',
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 6)
        self.assertEqual(self.stock.reserved_quantity, 0)
        self.assertEqual(StockAuditLog.objects.filter(
            reason=StockAuditLog.Reason.RESERVATION_CONSUMED,
            reference_number='ORDER-CONSUME-1',
        ).count(), 1)

    def test_return_enters_quarantine_not_sellable_stock(self):
        InventoryService.quarantine_return(
            branch=self.branch, product=self.product, quantity=2,
            triggered_by=self.actor, reference_number='RETURN-1',
            note='Awaiting inspection.',
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 10)
        self.assertEqual(self.stock.damaged_quantity, 2)
        self.assertEqual(self.stock.available_quantity, 10)


@skipUnlessDBFeature('has_select_for_update')
class PostgreSQLInventoryConcurrencyTests(TransactionTestCase):
    """Runs in PostgreSQL CI; SQLite skips because it cannot prove row locks."""

    reset_sequences = True

    def setUp(self):
        self.branch = Branch.objects.create(name='Concurrent Branch', location='Nakuru')
        self.actor = User.objects.create_user(
            username='concurrent_manager', phone_number='+254733699902',
            email='concurrent.manager@example.test', password='StrongPass123!',
            role=User.Role.INVENTORY_MANAGER, branch=self.branch,
        )
        category = Category.objects.create(name='Concurrent Items', slug='concurrent-items')
        self.product = Product.objects.create(
            name='Concurrent Product', slug='concurrent-product',
            category=category, price=Decimal('100.00'),
        )
        Stock.objects.create(branch=self.branch, product=self.product, quantity=5)

    def test_two_simultaneous_sales_cannot_oversell(self):
        branch_id = self.branch.id
        product_id = self.product.id
        actor_id = self.actor.id

        def deduct(reference):
            close_old_connections()
            try:
                InventoryService.adjust_stock(
                    branch=Branch.objects.get(id=branch_id),
                    product=Product.objects.get(id=product_id),
                    change_amount=-4,
                    reason=StockAuditLog.Reason.SALE,
                    triggered_by=User.objects.get(id=actor_id),
                    reference_number=reference,
                )
                return 'sold'
            except ValidationError:
                return 'blocked'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(deduct, ['CONCURRENT-1', 'CONCURRENT-2']))

        self.assertCountEqual(outcomes, ['sold', 'blocked'])
        stock = Stock.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(stock.quantity, 1)


class InventoryWorkspaceTests(TestCase):
    """Covers the staff-facing intake, transfer and stock-count journey."""

    def setUp(self):
        self.otc = Branch.objects.create(
            name='OTC Receiving Hub', location='OTC, Nairobi',
            receives_supplier_stock=True,
        )
        self.s18 = Branch.objects.create(
            name='Gaberone Plaza S18', location='Second floor, Gaberone Plaza',
        )
        self.b03 = Branch.objects.create(
            name='Gaberone Plaza B03', location='Gaberone Plaza',
        )
        self.otc_manager = User.objects.create_user(
            username='otc_workspace_manager', phone_number='+254733700001',
            email='otc.workspace@example.test', password='StrongPass123!',
            role=User.Role.INVENTORY_MANAGER, branch=self.otc,
        )
        self.b03_manager = User.objects.create_user(
            username='b03_workspace_manager', phone_number='+254733700002',
            email='b03.workspace@example.test', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.b03,
        )
        self.staff = User.objects.create_user(
            username='ordinary_workspace_staff', phone_number='+254733700003',
            email='staff.workspace@example.test', password='StrongPass123!',
            role=User.Role.STAFF, branch=self.b03,
        )
        self.super_admin = User.objects.create_superuser(
            username='workspace_super_admin', phone_number='+254733700004',
            email='super.workspace@example.test', password='StrongPass123!',
        )
        category = Category.objects.create(name='Workspace Stock', slug='workspace-stock')
        self.product = Product.objects.create(
            name='Canvas Travel Bag', slug='canvas-travel-bag',
            category=category, price=Decimal('2500.00'), sku='BAG-WORKSPACE',
        )

    def test_workspace_requires_an_inventory_role_and_has_compact_brand_link(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('inventory:inventory-workspace'))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.otc_manager)
        response = self.client.get(reverse('inventory:inventory-workspace'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inventory workspace')
        self.assertContains(response, 'aria-label="Emporium Plug home"')
        self.assertContains(response, 'Emporium<span class="font-medium text-brand-600">Plug</span>', html=True)
        self.assertContains(response, reverse('inventory:inventory-workspace'))

    def test_super_admin_can_switch_workspace_branch(self):
        self.client.force_login(self.super_admin)
        response = self.client.get(
            reverse('inventory:inventory-workspace'), {'branch': self.s18.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_branch'], self.s18)

    def test_intake_transfer_and_count_complete_through_workspace(self):
        self.client.force_login(self.otc_manager)
        response = self.client.post(reverse('inventory:workspace-intake'), {
            'workspace_branch': self.otc.pk,
            'supplier_name': 'Verified Supplier',
            'delivery_reference': 'DELIVERY-UI-001',
            'item': [f'p:{self.product.pk}'],
            'quantity': ['10'],
            'notes': 'Ten units physically checked.',
        })
        self.assertRedirects(
            response,
            f"{reverse('inventory:inventory-workspace')}?branch={self.otc.pk}",
        )
        self.assertEqual(
            Stock.objects.get(branch=self.otc, product=self.product).quantity, 10,
        )

        self.client.force_login(self.b03_manager)
        response = self.client.post(reverse('inventory:workspace-transfer-request'), {
            'workspace_branch': self.b03.pk,
            'from_branch': self.otc.pk,
            'to_branch': self.b03.pk,
            'item': f'p:{self.product.pk}',
            'quantity': 4,
            'notes': 'Replenish B03.',
        })
        self.assertEqual(response.status_code, 302)
        transfer = TransferRequest.objects.get()
        self.assertEqual(transfer.status, TransferRequest.Status.REQUESTED)

        self.client.force_login(self.otc_manager)
        self.client.post(
            reverse('inventory:workspace-transfer-approve', args=[transfer.pk]),
            {'workspace_branch': self.otc.pk},
        )
        self.client.post(
            reverse('inventory:workspace-transfer-dispatch', args=[transfer.pk]),
            {'workspace_branch': self.otc.pk},
        )
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TransferRequest.Status.DISPATCHED)

        self.client.force_login(self.b03_manager)
        self.client.post(
            reverse('inventory:workspace-transfer-receive', args=[transfer.pk]),
            {'workspace_branch': self.b03.pk, 'quantity': 4, 'note': 'Parcel checked.'},
        )
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TransferRequest.Status.RECEIVED)
        stock = Stock.objects.get(branch=self.b03, product=self.product)
        self.assertEqual(stock.quantity, 4)

        self.client.post(
            reverse('inventory:workspace-count-start'),
            {'workspace_branch': self.b03.pk, 'notes': 'Browser-style spot count.'},
        )
        count = StockCount.objects.get(branch=self.b03)
        line = count.lines.get()
        response = self.client.post(
            reverse('inventory:workspace-count-complete', args=[count.pk]),
            {'workspace_branch': self.b03.pk, f'line_{line.pk}': 4},
        )
        self.assertEqual(response.status_code, 302)
        count.refresh_from_db()
        self.assertEqual(count.status, StockCount.Status.COMPLETED)

    def test_branch_manager_spoofed_branch_is_ignored_for_adjustment(self):
        Stock.objects.create(branch=self.otc, product=self.product, quantity=2)
        self.client.force_login(self.b03_manager)
        response = self.client.post(reverse('inventory:workspace-adjustment'), {
            'workspace_branch': self.otc.pk,
            'item': f'p:{self.product.pk}',
            'reason': StockAuditLog.Reason.CORRECTION,
            'change_amount': 1,
            'reference_number': 'CROSS-BRANCH-ATTEMPT',
            'note': 'This must not be accepted.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Stock.objects.get(branch=self.otc, product=self.product).quantity, 2,
        )
        audit = StockAuditLog.objects.get(reference_number='CROSS-BRANCH-ATTEMPT')
        self.assertEqual(audit.branch, self.b03)
