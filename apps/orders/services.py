# apps/orders/services.py
from decimal import Decimal
import hashlib
from django.db import transaction
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db.models import Q
from inventory.services import InventoryService
from inventory.models import StockAuditLog
from .models import Order, OrderItem, OrderStatusHistory
from .transitions import OrderTransitionService
class POSSalesService:
    """
    Atomic service layer for walk-in POS sale processing.
    All walk-in sales go through process_walk_in_sale() — never create Orders directly.
    """

    @staticmethod
    def _authorize_manager_credentials(
            *, manager_username, manager_password, requesting_cashier,
            action_type, context_label, ip_address=None,
        ):
            """
            Shared manager re-authentication core for any POS elevated-privilege
            flow (discounts, voids). Re-authenticates live manager credentials --
            a cashier session must never self-grant authority via role alone.
            Accepts BRANCH_MANAGER (same branch as requesting_cashier only) or
            SUPER_ADMIN (any branch). Every attempt -- denied or granted -- is
            logged via AuditTrackingService under the caller-supplied action_type.
            Returns the authenticated manager User instance.
            Raises ValidationError with .code in {'invalid_credentials','branch_mismatch'}.
            """
            from analytics.services import AuditTrackingService
            from users.models import User
            from users.rate_limit import check_rate_limit
            from users.security import AuthenticationSecurityService

            identity = (manager_username or '').strip()
            identity_key = hashlib.sha256(identity.lower().encode('utf-8')).hexdigest()
            candidate = User.objects.filter(
                Q(username=identity) | Q(phone_number=identity) | Q(email__iexact=identity)
            ).order_by('id').first()
            if candidate and AuthenticationSecurityService.is_locked(candidate):
                raise ValidationError(
                    "Manager authorization is temporarily locked. Try again later.",
                    code='invalid_credentials',
                )

            authenticated_manager = authenticate(username=identity, password=manager_password)

            if not authenticated_manager or authenticated_manager.role not in [
                User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN,
            ]:
                throttled = False
                try:
                    check_rate_limit(
                        f"ratelimit:manager_reauth:{ip_address or 'unknown'}:{identity_key}",
                        limit=5,
                        window_seconds=900,
                    )
                except ValidationError:
                    throttled = True
                AuthenticationSecurityService.record_failure(candidate)
                AuditTrackingService.log_action(
                    user=requesting_cashier,
                    action_type=action_type,
                    description=(
                        f"DENIED: Invalid manager override credentials supplied by "
                        f"cashier_user_id={requesting_cashier.pk} for {context_label}."
                    ),
                    ip_address=ip_address,
                )
                if throttled:
                    raise ValidationError(
                        "Too many manager authorization attempts. Try again later.",
                        code='invalid_credentials',
                    )
                raise ValidationError("Invalid manager authorization credentials", code='invalid_credentials')

            AuthenticationSecurityService.clear_failures(authenticated_manager)

            if (
                authenticated_manager.role == User.Role.BRANCH_MANAGER
                and authenticated_manager.branch_id != requesting_cashier.branch_id
            ):
                AuditTrackingService.log_action(
                    user=requesting_cashier,
                    action_type=action_type,
                    description=(
                        f"DENIED: Manager user_id={authenticated_manager.pk} is not "
                        f"registered to cashier branch_id={requesting_cashier.branch_id} "
                        f"for {context_label}."
                    ),
                    ip_address=ip_address,
                )
                raise ValidationError(
                    "Authorizing manager is not registered to this physical branch workspace node.",
                    code='branch_mismatch',
                )

            AuditTrackingService.log_action(
                user=authenticated_manager,
                action_type=action_type,
                description=(
                    f"GRANTED: Manager user_id={authenticated_manager.pk} authorized "
                    f"{context_label} for cashier_user_id={requesting_cashier.pk}."
                ),
                ip_address=ip_address,
            )
            return authenticated_manager

    @staticmethod
    def authorize_discount_override(*, manager_username, manager_password, requesting_cashier, ip_address=None):
            from analytics.models import AuditLog
            return POSSalesService._authorize_manager_credentials(
                manager_username=manager_username,
                manager_password=manager_password,
                requesting_cashier=requesting_cashier,
                action_type=AuditLog.ActionTypes.DISCOUNT_APPLIED,
                context_label="a discount override",
                ip_address=ip_address,
            )

    @staticmethod
    def void_sale(
        *, order_number, branch, requesting_staff,
        manager_username, manager_password, void_reason, ip_address=None,
    ) -> Order:
        """
        Voids a COMPLETED walk-in sale under manager PIN authorization.
        Authorization happens OUTSIDE the atomic block deliberately -- a
        DENIED audit log must persist even when the void itself never
        proceeds. Only the order/stock mutation is atomic.
        """
        from analytics.models import AuditLog

        if not void_reason or not void_reason.strip():
            raise ValidationError(
                "POS Refusal: A void reason is mandatory and will be permanently logged."
            )

        authenticated_manager = POSSalesService._authorize_manager_credentials(
            manager_username=manager_username,
            manager_password=manager_password,
            requesting_cashier=requesting_staff,
            action_type=AuditLog.ActionTypes.STOCK_VOID,
            context_label=f"a sale void (order {order_number})",
            ip_address=ip_address,
        )

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(
                    order_number=order_number,
                    branch=branch,
                )
            except Order.DoesNotExist:
                raise ValidationError("Void Refusal: Order not found at this branch.")

            if order.status != Order.Status.COMPLETED:
                raise ValidationError(
                    f"Void Refusal: Only COMPLETED sales can be voided. "
                    f"Current status: {order.get_status_display()}."
                )
            if order.order_type != Order.OrderType.WALK_IN:
                raise ValidationError("Void Refusal: Only walk-in POS sales are voided through this flow.")
            if order.pos_shift_id and order.pos_shift.status != 'OPEN':
                raise ValidationError(
                    'Void Refusal: This sale belongs to a closed shift. Use the audited return/correction workflow.'
                )

            for item in order.items.select_related('variant', 'product').all():
                InventoryService.adjust_stock(
                    branch=order.branch,
                    change_amount=int(item.quantity),
                    reason=StockAuditLog.Reason.VOID_REVERSAL,
                    triggered_by=authenticated_manager,
                    variant=item.variant,
                    product=item.product,
                    reference_number=order.order_number,
                    note=f"Stock restored -- sale voided by manager '{authenticated_manager.username}'.",
                )

            order = OrderTransitionService.transition(
                order=order,
                to_status=Order.Status.VOIDED,
                note=f"Voided by manager '{authenticated_manager.username}'. Reason: {void_reason.strip()}",
                changed_by=authenticated_manager,
                extra_updates={'void_reason': void_reason.strip()},
            )

            from reports.models import OperationalAuditRiskLog
            OperationalAuditRiskLog.objects.create(
                branch=order.branch,
                initiator=authenticated_manager,
                action_type='ORDER_VOID',
                severity=OperationalAuditRiskLog.RiskSeverity.HIGH,
                target_record_id=str(order.pk),
                justification_trail=void_reason.strip(),
                metadata_payload={
                    'requesting_staff_id': requesting_staff.pk,
                    'shift_id': order.pos_shift_id,
                    'amount': str(order.total_payable),
                },
            )

            order_id_str = str(order.id)
            manager_username_final = authenticated_manager.username
            reason_final = void_reason.strip()
            from notifications.tasks import send_void_processed_alert
            transaction.on_commit(
                lambda: send_void_processed_alert.delay(order_id_str, manager_username_final, reason_final)
            )

        return order

    @staticmethod
    @transaction.atomic
    def process_walk_in_sale(
        branch,
        cashier,
        customer_phone: str,
        items_payload: list,
        discount_amount=Decimal('0.00'),
        payment_method=Order.PaymentMethod.CASH,
        payment_reference=None,
        amount_received=None,
        manager_authorized_by=None,
        payment_verification_reason='',
        pos_shift=None,
        discount_reason='',
        customer_name: str = '',
        coupon_code: str = None,
    ) -> Order:
        """
        Executes a complete, atomic walk-in sale transaction.

        items_payload format:
            [
                {'variant': ProductVariantObject, 'quantity': 2},   # variant product
                {'product': ProductObject, 'quantity': 1},           # simple product
            ]

        Transaction guarantees:
        - If stock deduction fails on ANY item, the entire order is rolled back
        - If order creation fails, no stock is deducted
        - SMS receipt is triggered asynchronously AFTER the transaction commits

        Raises:
            ValidationError: phone missing, empty cart, insufficient stock,
                             discount exceeds subtotal, unauthorized discount
        """
        # --- Guard: phone number ---
        from users.identifiers import normalize_phone_number
        try:
            normalized_customer_phone = normalize_phone_number(customer_phone)
        except ValidationError:
            raise ValidationError(
                "POS Refusal: A valid customer phone number is required for all walk-in sales."
            ) from None

        # --- Guard: empty cart ---
        if not items_payload:
            raise ValidationError(
                "POS Refusal: Cannot process a transaction with an empty product tray."
            )

        from reports.models import POSShift
        try:
            locked_shift = POSShift.objects.select_for_update().get(
                pk=getattr(pos_shift, 'pk', None),
                cashier=cashier,
                branch=branch,
                status=POSShift.Status.OPEN,
            )
        except POSShift.DoesNotExist:
            raise ValidationError('POS Refusal: Open your shift before completing a sale.') from None

        # --- Guard: discount authorization ---
        discount_amount = Decimal(str(discount_amount))
        if discount_amount > 0:
            from users.models import User
            if manager_authorized_by is None or manager_authorized_by.role not in [
                User.Role.BRANCH_MANAGER,
                User.Role.SUPER_ADMIN,
            ]:
                raise ValidationError(
                    "POS Refusal: Staff profiles cannot apply discounts without manager authorization."
                )

            if len(str(discount_reason or '').strip()) < 5:
                raise ValidationError('POS Refusal: Record a reason for the manager discount.')
            if coupon_code:
                raise ValidationError(
                    'POS Refusal: Manual discounts and coupons cannot be stacked.'
                )

        if payment_method == Order.PaymentMethod.PAYBILL:
            if not payment_reference:
                raise ValidationError('POS Refusal: A verified M-Pesa receipt is required.')
            if manager_authorized_by is None:
                raise ValidationError('POS Refusal: Manager verification is required for Paybill sales.')
            if len(str(payment_verification_reason or '').strip()) < 10:
                raise ValidationError(
                    'POS Refusal: Record how the Paybill payment was verified.'
                )

        from catalog.pricing import QuantityPricingService
        product_quantities = {}
        for item in items_payload:
            variant = item.get('variant')
            product = item.get('product')
            if bool(variant) == bool(product):
                raise ValidationError(
                    'POS Refusal: Each cart item must identify one product or one variant.'
                )
            catalog_product = variant.product if variant else product
            product_quantities[catalog_product.pk] = (
                product_quantities.get(catalog_product.pk, 0) + int(item['quantity'])
            )

        priced_items = []
        for item in items_payload:
            variant = item.get('variant')
            product = item.get('product')
            catalog_product = variant.product if variant else product
            combined_quantity = product_quantities[catalog_product.pk]
            if combined_quantity < catalog_product.minimum_order_quantity:
                shortfall = catalog_product.minimum_order_quantity - combined_quantity
                raise ValidationError(
                    f'POS Refusal: Add {shortfall} more {catalog_product.name}; '
                    f'the minimum is {catalog_product.minimum_order_quantity}. '
                    'Sizes and colours count together.'
                )
            regular_price = variant.effective_price if variant else product.price
            quote = QuantityPricingService.quote(
                product=catalog_product,
                regular_unit_price=regular_price,
                current_unit_price=regular_price,
                product_quantity=combined_quantity,
            )
            priced_items.append((item, quote))

        has_quantity_price = any(quote.wholesale_applied for _, quote in priced_items)
        if has_quantity_price and (discount_amount > 0 or coupon_code):
            raise ValidationError(
                'POS Refusal: Quantity pricing cannot be combined with a coupon or manager discount.'
            )

        # --- Create order (PENDING until fully processed) ---
        order = Order.objects.create(
            branch=branch,
            order_type=Order.OrderType.WALK_IN,
            sales_channel=Order.SalesChannel.POS,
            customer_phone=normalized_customer_phone,
            customer_name=customer_name.strip(),
            # Financial values are finalized only after every line has been
            # priced. Keep the draft row internally consistent with the DB
            # constraint while the transaction is still being assembled.
            discount_amount=Decimal('0.00'),
            payment_method=payment_method,
            payment_reference=payment_reference,
            processed_by=cashier,
            pos_shift=locked_shift,
            status=Order.Status.PENDING,
        )

        running_subtotal = Decimal('0.00')

        
        for item, price_quote in priced_items:
            variant = item.get('variant')
            product = item.get('product')
            qty = item['quantity']

            # Validate item structure — exactly one of variant or product
            if variant and product:
                raise ValidationError(
                    "POS Refusal: An item cannot reference both a variant and a product."
                )
            if not variant and not product:
                raise ValidationError(
                    "POS Refusal: Each item must reference either a variant or a product."
                )

            # Lock price at this exact moment — immune to future price changes
            locked_price = price_quote.unit_price

            order_item = OrderItem(
                order=order,
                variant=variant,
                product=product,
                quantity=qty,
                unit_price=locked_price,
                regular_unit_price=price_quote.regular_unit_price,
                pricing_source=price_quote.source,
                quantity_tier_minimum=price_quote.tier_minimum,
                quantity_discount_percentage=price_quote.discount_percentage,
            )
            order_item.full_clean()
            order_item.save()

            running_subtotal += order_item.total_price

            # Route to InventoryService — handles both variant and product
            InventoryService.adjust_stock(
                variant=variant,
                product=product,
                branch=branch,
                change_amount=-int(qty),
                reason=StockAuditLog.Reason.SALE,
                triggered_by=cashier,
                reference_number=order.order_number,
            )

        # --- Guard: discount cannot exceed subtotal ---
        if discount_amount > running_subtotal:
            raise ValidationError(
                "POS Refusal: Discount value cannot exceed the total cart value."
            )
        # --- Finalize order ---
        order.subtotal = running_subtotal
        order.discount_amount = discount_amount
        order.total_payable = running_subtotal - discount_amount
        order.save(update_fields=['subtotal', 'discount_amount', 'total_payable'])
        if coupon_code:
            from marketing.services import PromotionService
            order = PromotionService.validate_and_apply_coupon_campaign(order, coupon_code)
        if payment_method == Order.PaymentMethod.CASH:
            try:
                tendered = Decimal(str(amount_received)).quantize(Decimal('0.01'))
            except Exception:
                raise ValidationError('POS Refusal: Enter the cash amount received.') from None
            if tendered < order.total_payable:
                raise ValidationError(
                    f'POS Refusal: Cash received is below the payable total of KES {order.total_payable}.'
                )
            order.amount_received = tendered
            order.change_due = tendered - order.total_payable
            order.save(update_fields=['amount_received', 'change_due', 'updated_at'])
        # --- Finalize status through the shared lifecycle policy ---
        order = OrderTransitionService.transition(
            order=order,
            to_status=Order.Status.COMPLETED,
            note="Walk-in sale completed successfully.",
            changed_by=cashier,
        )

        if payment_method == Order.PaymentMethod.PAYBILL:
            from reports.models import OperationalAuditRiskLog
            OperationalAuditRiskLog.objects.create(
                branch=branch,
                initiator=manager_authorized_by,
                action_type='MANUAL_MPESA_MATCH',
                severity=OperationalAuditRiskLog.RiskSeverity.HIGH,
                target_record_id=str(order.pk),
                justification_trail=str(payment_verification_reason).strip(),
                metadata_payload={
                    'order_id': order.pk,
                    'cashier_id': cashier.pk,
                    'amount': str(order.total_payable),
                    'channel': 'WALK_IN_POS',
                },
            )

        if discount_amount > 0:
            from reports.models import OperationalAuditRiskLog
            OperationalAuditRiskLog.objects.create(
                branch=branch,
                initiator=manager_authorized_by,
                action_type='POS_DISCOUNT_APPROVED',
                severity=OperationalAuditRiskLog.RiskSeverity.MEDIUM,
                target_record_id=str(order.pk),
                justification_trail=str(discount_reason).strip(),
                metadata_payload={
                    'cashier_id': cashier.pk,
                    'discount_amount': str(discount_amount),
                    'shift_id': locked_shift.pk,
                },
            )

        # --- Trigger async SMS receipt (non-blocking, fires after transaction commits) ---
        # Using transaction.on_commit ensures the SMS fires AFTER the DB transaction
        # is fully committed — not during it. If the transaction rolls back, no SMS is sent.
        from notifications.tasks import send_walkin_receipt_sms
        transaction.on_commit(lambda: send_walkin_receipt_sms.delay(str(order.id)))

        return order
