import base64
import logging
import requests
import environ
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from requests.auth import HTTPBasicAuth
from .models import MpesaTransaction

env = environ.Env()
logger = logging.getLogger(__name__)


class PaymentSettlementService:
    """Apply idempotent M-Pesa outcomes and their inventory effects."""

    @classmethod
    @transaction.atomic
    def confirm(
        cls,
        transaction_id,
        *,
        amount=None,
        receipt_number=None,
        phone_number=None,
        raw_callback_payload=None,
        confirmation_method=MpesaTransaction.ConfirmationMethod.AUTO_CALLBACK,
        confirmed_by=None,
    ):
        from orders.inventory import OrderInventoryService
        from orders.models import Order
        from orders.transitions import OrderTransitionService

        payment = MpesaTransaction.objects.select_for_update().select_related('order').get(
            id=transaction_id,
        )
        confirmable_statuses = {
            MpesaTransaction.Status.PENDING,
            MpesaTransaction.Status.QUERY_CONFIRMED,
            MpesaTransaction.Status.RECONCILIATION_REQUIRED,
        }
        if payment.status not in confirmable_statuses:
            return 'already_resolved'

        order = Order.objects.select_for_update().get(id=payment.order_id)
        try:
            received_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            received_amount = None

        receipt_number = str(receipt_number or '').strip().upper()
        expected_amount = payment.expected_amount or order.total_payable
        evidence_error = None
        if received_amount is None:
            evidence_error = 'Missing or invalid paid amount.'
        elif received_amount != expected_amount:
            evidence_error = (
                f"Amount mismatch: expected KES {expected_amount}, received KES {received_amount}."
            )
        elif not receipt_number:
            evidence_error = 'Missing provider receipt number.'
        elif MpesaTransaction.objects.exclude(pk=payment.pk).filter(
            mpesa_receipt_number=receipt_number,
        ).exists():
            evidence_error = 'Provider receipt number is already assigned to another payment.'

        if evidence_error:
            payment.amount = received_amount
            payment.raw_callback_payload = raw_callback_payload
            payment.failure_reason = evidence_error
            payment.status = MpesaTransaction.Status.RECONCILIATION_REQUIRED
            payment.save(update_fields=[
                'amount', 'raw_callback_payload', 'failure_reason', 'status', 'updated_at',
            ])
            return 'reconciliation_required'

        payment.amount = received_amount
        payment.mpesa_receipt_number = receipt_number
        payment.phone_number = (
            str(phone_number) if phone_number is not None else payment.phone_number
        )
        payment.raw_callback_payload = raw_callback_payload
        payment.failure_reason = None
        payment.status = MpesaTransaction.Status.SUCCESS
        payment.confirmation_method = confirmation_method
        payment.confirmed_by = confirmed_by
        payment.save(update_fields=[
            'amount', 'mpesa_receipt_number', 'phone_number',
            'raw_callback_payload', 'failure_reason', 'status',
            'confirmation_method', 'confirmed_by', 'updated_at',
        ])

        actor = order.customer or order.processed_by
        OrderInventoryService.consume_reservations(
            order=order,
            actor=actor,
            note='Reservation consumed after M-Pesa payment confirmation.',
        )
        OrderTransitionService.transition(
            order=order,
            to_status=Order.Status.PROCESSING,
            changed_by=actor,
            note='M-Pesa payment confirmed.',
            extra_updates={'payment_reference': payment.mpesa_receipt_number},
        )
        return 'confirmed'

    @classmethod
    @transaction.atomic
    def mark_query_confirmed(cls, transaction_id, *, description=''):
        payment = MpesaTransaction.objects.select_for_update().get(id=transaction_id)
        if payment.status != MpesaTransaction.Status.PENDING:
            return 'already_resolved'
        payment.status = MpesaTransaction.Status.QUERY_CONFIRMED
        payment.query_confirmed_at = timezone.now()
        payment.failure_reason = (
            'Provider query reports success; awaiting receipt-level callback evidence. '
            f'{description}'
        ).strip()
        payment.save(update_fields=[
            'status', 'query_confirmed_at', 'failure_reason', 'updated_at',
        ])
        return 'query_confirmed'

    @classmethod
    @transaction.atomic
    def fail(cls, transaction_id, *, reason, raw_callback_payload=None):
        from orders.inventory import OrderInventoryService
        from orders.models import Order
        from orders.transitions import OrderTransitionService
        from users.models import User

        payment = MpesaTransaction.objects.select_for_update().select_related('order').get(
            id=transaction_id,
        )
        if payment.status == MpesaTransaction.Status.QUERY_CONFIRMED:
            payment.status = MpesaTransaction.Status.RECONCILIATION_REQUIRED
            payment.failure_reason = (
                'Conflicting provider evidence: query reported success but callback reported failure. '
                f'{reason}'
            )
            payment.raw_callback_payload = raw_callback_payload
            payment.save(update_fields=[
                'status', 'failure_reason', 'raw_callback_payload', 'updated_at',
            ])
            return 'reconciliation_required'
        if payment.status != MpesaTransaction.Status.PENDING:
            return 'already_resolved'

        order = Order.objects.select_for_update().get(id=payment.order_id)
        payment.status = MpesaTransaction.Status.FAILED
        payment.failure_reason = reason
        payment.raw_callback_payload = raw_callback_payload
        payment.save(update_fields=[
            'status', 'failure_reason', 'raw_callback_payload', 'updated_at',
        ])

        actor = order.customer or order.processed_by or User.get_system_account()
        OrderInventoryService.release_reservations(
            order=order,
            actor=actor,
            note='Reservation released after terminal M-Pesa payment failure.',
        )
        OrderTransitionService.transition(
            order=order,
            to_status=Order.Status.CANCELLED,
            changed_by=actor,
            note=f'M-Pesa payment failed: {reason}',
            extra_updates={'void_reason': f'M-Pesa payment failed: {reason}'},
        )
        return 'failed'


class ManualPaymentConfirmationService:
    """Confirm externally verified M-Pesa evidence under manager re-authentication."""

    @classmethod
    def confirm(
        cls,
        *,
        payment_id,
        requesting_staff,
        manager_username,
        manager_password,
        amount,
        receipt_number,
        reason,
        ip_address=None,
    ):
        from analytics.models import AuditLog
        from orders.services import POSSalesService
        from reports.models import OperationalAuditRiskLog
        from users.models import User

        reason = str(reason or '').strip()
        if len(reason) < 10:
            raise ValidationError('A clear reconciliation reason of at least 10 characters is required.')
        if requesting_staff.role not in {
            User.Role.STAFF,
            User.Role.BRANCH_MANAGER,
            User.Role.SUPER_ADMIN,
        }:
            raise ValidationError('Only authorized staff may reconcile payments.')

        try:
            payment = MpesaTransaction.objects.select_related('order').get(pk=payment_id)
        except MpesaTransaction.DoesNotExist:
            raise ValidationError('Payment record not found.') from None
        if (
            requesting_staff.role != User.Role.SUPER_ADMIN
            and requesting_staff.branch_id != payment.order.branch_id
        ):
            raise ValidationError('Payment reconciliation is restricted to the order branch.')

        manager = POSSalesService._authorize_manager_credentials(
            manager_username=manager_username,
            manager_password=manager_password,
            requesting_cashier=requesting_staff,
            action_type=AuditLog.ActionTypes.MANUAL_PAYMENT_CONFIRMATION,
            context_label=f'manual M-Pesa reconciliation for payment {payment.pk}',
            ip_address=ip_address,
        )
        normalized_receipt = str(receipt_number or '').strip().upper()
        if payment.submitted_reference and normalized_receipt != payment.submitted_reference:
            raise ValidationError('Verified receipt does not match the customer-submitted reference.')

        with transaction.atomic():
            outcome = PaymentSettlementService.confirm(
                payment.pk,
                amount=amount,
                receipt_number=normalized_receipt,
                confirmation_method=MpesaTransaction.ConfirmationMethod.MANUAL_STAFF,
                confirmed_by=manager,
                raw_callback_payload={
                    'manual_reconciliation': True,
                    'customer_reference_present': bool(payment.submitted_reference),
                },
            )
            if outcome != 'confirmed':
                raise ValidationError(
                    'Payment could not be confirmed; review the amount, receipt, and current state.'
                )
            OperationalAuditRiskLog.objects.create(
                branch=payment.order.branch,
                initiator=manager,
                action_type='MANUAL_MPESA_MATCH',
                severity=OperationalAuditRiskLog.RiskSeverity.HIGH,
                target_record_id=str(payment.pk),
                justification_trail=reason,
                metadata_payload={
                    'order_id': payment.order_id,
                    'requesting_staff_id': requesting_staff.pk,
                    'amount': str(amount),
                },
            )
            payment.webhook_events.filter(
                processing_status__in=[
                    'REVIEW_REQUIRED',
                    'PROCESSING_FAILED',
                ],
            ).update(
                processing_status='RESOLVED',
                resolved_by=manager,
                resolved_at=timezone.now(),
                resolution_note=f'Resolved by audited manual payment confirmation: {reason}',
            )
        return MpesaTransaction.objects.get(pk=payment.pk)


class WebhookEventReviewService:
    """Close callback-inbox items only after manager re-authentication and audit."""

    @classmethod
    def resolve(
        cls,
        *,
        event_id,
        requesting_staff,
        manager_username,
        manager_password,
        resolution_note,
        ip_address=None,
    ):
        from analytics.models import AuditLog
        from orders.services import POSSalesService
        from payments.models import MpesaWebhookEvent
        from reports.models import OperationalAuditRiskLog
        from users.models import User

        note = str(resolution_note or '').strip()
        if len(note) < 10:
            raise ValidationError('A resolution note of at least 10 characters is required.')
        try:
            event = MpesaWebhookEvent.objects.select_related(
                'payment__order',
            ).get(pk=event_id)
        except MpesaWebhookEvent.DoesNotExist:
            raise ValidationError('Webhook event not found.') from None

        branch = event.payment.order.branch if event.payment_id else None
        if branch and (
            requesting_staff.role != User.Role.SUPER_ADMIN
            and requesting_staff.branch_id != branch.pk
        ):
            raise ValidationError('Webhook review is restricted to the payment branch.')
        if not branch and requesting_staff.role != User.Role.SUPER_ADMIN:
            raise ValidationError('Only a super-admin may resolve an unmatched webhook.')

        manager = POSSalesService._authorize_manager_credentials(
            manager_username=manager_username,
            manager_password=manager_password,
            requesting_cashier=requesting_staff,
            action_type=AuditLog.ActionTypes.PAYMENT_WEBHOOK_REVIEW,
            context_label=f'M-Pesa webhook event review {event.pk}',
            ip_address=ip_address,
        )
        if not branch and manager.role != User.Role.SUPER_ADMIN:
            raise ValidationError('An unmatched webhook requires super-admin authorization.')

        with transaction.atomic():
            event = MpesaWebhookEvent.objects.select_for_update().get(pk=event.pk)
            if event.processing_status == MpesaWebhookEvent.ProcessingStatus.RESOLVED:
                return event
            if event.processing_status not in {
                MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
                MpesaWebhookEvent.ProcessingStatus.PROCESSING_FAILED,
            }:
                raise ValidationError('Only review or failed webhook events can be resolved.')
            event.processing_status = MpesaWebhookEvent.ProcessingStatus.RESOLVED
            event.resolved_by = manager
            event.resolved_at = timezone.now()
            event.resolution_note = note
            event.save(update_fields=[
                'processing_status', 'resolved_by', 'resolved_at',
                'resolution_note', 'last_received_at',
            ])
            OperationalAuditRiskLog.objects.create(
                branch=branch,
                initiator=manager,
                action_type='MPESA_WEBHOOK_REVIEW',
                severity=OperationalAuditRiskLog.RiskSeverity.HIGH,
                target_record_id=str(event.pk),
                justification_trail=note,
                metadata_payload={
                    'payment_id': event.payment_id,
                    'original_outcome': event.outcome,
                    'requesting_staff_id': requesting_staff.pk,
                },
            )
        return event


class MpesaDarajaService:
    """
    Core client service executing outgoing integration calls to Safaricom Daraja Gateways.
    """
    
    @classmethod
    def base_url(cls):
        environment = env('MPESA_ENVIRONMENT', default='sandbox').strip().lower()
        if environment == 'sandbox':
            return 'https://sandbox.safaricom.co.ke'
        if environment == 'production':
            return 'https://api.safaricom.co.ke'
        raise ValidationError('MPESA_ENVIRONMENT must be sandbox or production.')

    @classmethod
    def generate_access_token(cls):
        """
        Authenticates with Safaricom using App Keys to obtain a valid Bearer token.
        """
        endpoint = f"{cls.base_url()}/oauth/v1/generate?grant_type=client_credentials"
        consumer_key = env('MPESA_CONSUMER_KEY')
        consumer_secret = env('MPESA_CONSUMER_SECRET')
        
        try:
            response = requests.get(
                endpoint, 
                auth=HTTPBasicAuth(consumer_key, consumer_secret), 
                timeout=10
            )
            response.raise_for_status()
            return response.json()['access_token']
        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.error('M-Pesa access-token request failed | ExceptionType=%s', type(exc).__name__)
            raise ValidationError('M-Pesa is temporarily unavailable. Please try again.') from None


    @classmethod
    def query_stk_push_status(cls, checkout_request_id):
        """
        STK Push Query API — callback retry queue (§9 Scenario 2). Returns
        the raw Daraja response dict; caller interprets ResultCode.
        Note: unlike the async push callback, this response never includes
        CallbackMetadata (receipt number) even on success -- confirmed
        payments via polling are flagged AUTO_CALLBACK but leave
        mpesa_receipt_number blank pending eventual webhook arrival or
        manual staff reconciliation.
        """
        access_token = cls.generate_access_token()
        endpoint = f"{cls.base_url()}/mpesa/stkpushquery/v1/query"
        shortcode = env('MPESA_SHORTCODE')
        passkey = env('MPESA_PASSKEY')
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = f"{shortcode}{passkey}{timestamp}"
        b64_encoded_password = base64.b64encode(password_str.encode()).decode('utf-8')
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {
            "BusinessShortCode": shortcode,
            "Password": b64_encoded_password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning('M-Pesa status query failed | ExceptionType=%s', type(exc).__name__)
            raise ValidationError('M-Pesa payment status is temporarily unavailable.') from None

    @classmethod
    @transaction.atomic
    def _prepare_initiation(cls, order, formatted_phone, expected_amount):
        from orders.models import Order

        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status != Order.Status.PENDING:
            raise ValidationError('This order is no longer awaiting payment.')
        if locked_order.payment_method != Order.PaymentMethod.MPESA_STK:
            raise ValidationError('This order is not configured for M-Pesa STK payment.')

        payment = MpesaTransaction.objects.filter(order=locked_order).first()
        if payment and payment.status in {
            MpesaTransaction.Status.INITIATING,
            MpesaTransaction.Status.PENDING,
            MpesaTransaction.Status.QUERY_CONFIRMED,
            MpesaTransaction.Status.RECONCILIATION_REQUIRED,
            MpesaTransaction.Status.SUCCESS,
        }:
            return payment, False

        if payment is None:
            local_id = uuid.uuid4().hex
            payment = MpesaTransaction.objects.create(
                order=locked_order,
                merchant_request_id=f'LOCAL-MERCHANT-{local_id}',
                checkout_request_id=f'LOCAL-CHECKOUT-{local_id}',
                status=MpesaTransaction.Status.INITIATING,
                expected_amount=expected_amount,
                requested_phone_number=formatted_phone,
                account_reference=locked_order.order_number,
                initiation_attempts=1,
            )
        else:
            payment.status = MpesaTransaction.Status.INITIATING
            payment.expected_amount = expected_amount
            payment.requested_phone_number = formatted_phone
            payment.account_reference = locked_order.order_number
            payment.initiation_attempts += 1
            payment.failure_reason = None
            payment.save(update_fields=[
                'status', 'expected_amount', 'requested_phone_number',
                'account_reference', 'initiation_attempts', 'failure_reason', 'updated_at',
            ])
        return payment, True

    @classmethod
    def _record_initiation_failure(cls, payment_id, message):
        MpesaTransaction.objects.filter(
            pk=payment_id,
            status=MpesaTransaction.Status.INITIATING,
        ).update(
            status=MpesaTransaction.Status.INITIATION_FAILED,
            failure_reason=message,
        )

    @classmethod
    def initiate_stk_push(cls, order, phone_number):
        """
        Dispatches an automated Lipa Na M-Pesa Online STK Push pop-up prompt to a target device.
        """
        from users.identifiers import normalize_phone_number

        normalized_phone = normalize_phone_number(phone_number)
        formatted_phone = normalized_phone.lstrip('+')
        payable_decimal = Decimal(str(order.total_payable)).quantize(Decimal('0.01'))
        if payable_decimal <= 0:
            raise ValidationError('M-Pesa payment amount must be greater than zero.')
        if payable_decimal != payable_decimal.to_integral_value():
            raise ValidationError(
                'M-Pesa STK payment requires a whole-KES total. Please contact support.'
            )

        payment, should_send = cls._prepare_initiation(
            order,
            normalized_phone,
            payable_decimal,
        )
        if not should_send:
            return payment

        try:
            access_token = cls.generate_access_token()
            shortcode = env('MPESA_SHORTCODE')
            passkey = env('MPESA_PASSKEY')
            callback_url = env('MPESA_CALLBACK_URL')
        except Exception as exc:
            cls._record_initiation_failure(payment.id, 'M-Pesa configuration or authentication failed.')
            if isinstance(exc, ValidationError):
                raise
            logger.error('M-Pesa configuration unavailable | ExceptionType=%s', type(exc).__name__)
            raise ValidationError('M-Pesa is temporarily unavailable. Please try again.') from None

        endpoint = f"{cls.base_url()}/mpesa/stkpush/v1/processrequest"

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = f"{shortcode}{passkey}{timestamp}"
        b64_encoded_password = base64.b64encode(password_str.encode()).decode('utf-8')

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        
        payable_amount = int(payable_decimal)

        payload = {
            "BusinessShortCode": shortcode,
            "Password": b64_encoded_password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline", # Use CustomerBuyGoodsOnline for Till layouts
            "Amount": payable_amount,
            "PartyA": formatted_phone,
            "PartyB": shortcode,
            "PhoneNumber": formatted_phone,
            "CallBackURL": callback_url,
            "AccountReference": order.order_number,
            "TransactionDesc": f"Payment for Order {order.order_number}"
        }

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('ResponseCode') == '0':
                merchant_request_id = response_data.get('MerchantRequestID')
                checkout_request_id = response_data.get('CheckoutRequestID')
                if not merchant_request_id or not checkout_request_id:
                    raise ValidationError('M-Pesa did not return payment tracking identifiers.')
                with transaction.atomic():
                    mpesa_txn = MpesaTransaction.objects.select_for_update().get(pk=payment.pk)
                    mpesa_txn.merchant_request_id = merchant_request_id
                    mpesa_txn.checkout_request_id = checkout_request_id
                    mpesa_txn.status = MpesaTransaction.Status.PENDING
                    mpesa_txn.failure_reason = None
                    mpesa_txn.save(update_fields=[
                        'merchant_request_id', 'checkout_request_id', 'status',
                        'failure_reason', 'updated_at',
                    ])
                # Callback retry queue (§9 Scenario 2) -- schedule the first
                # poll attempt 2 minutes out, giving the customer time to
                # enter their PIN before we check. Broker-resilient: a
                # scheduling failure never blocks the checkout response.
                try:
                    from .tasks import poll_pending_stk_push_status, POLL_INTERVAL_SECONDS
                    poll_pending_stk_push_status.apply_async(
                        args=[mpesa_txn.id], countdown=POLL_INTERVAL_SECONDS,
                    )
                except Exception as sched_error:
                    logger.error(
                        "Could not schedule STK polling | PaymentID=%s | ExceptionType=%s",
                        mpesa_txn.id,
                        type(sched_error).__name__,
                    )
                return mpesa_txn
            else:
                cls._record_initiation_failure(
                    payment.id,
                    response_data.get('ResponseDescription', 'M-Pesa rejected the request.'),
                )
                raise ValidationError('M-Pesa could not start this payment. Please try again.')
                
        except ValidationError:
            cls._record_initiation_failure(payment.id, 'M-Pesa initiation response was incomplete.')
            raise
        except (requests.RequestException, ValueError, KeyError) as exc:
            cls._record_initiation_failure(payment.id, 'M-Pesa initiation request failed.')
            logger.error('M-Pesa initiation failed | PaymentID=%s | ExceptionType=%s', payment.id, type(exc).__name__)
            raise ValidationError('M-Pesa is temporarily unavailable. Please try again.') from None
