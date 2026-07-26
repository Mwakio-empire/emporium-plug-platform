from django.test import TestCase

# Create your tests here.
import json
import os
import requests
from decimal import Decimal
from unittest.mock import Mock, patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import Stock, StockAuditLog
from orders.models import Order, OrderItem, OrderStatusHistory
from payments.models import MpesaTransaction, MpesaWebhookEvent
from payments.services import MpesaDarajaService
from reports.models import OperationalAuditRiskLog

User = get_user_model()


class MpesaInitiationLifecycleTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Initiation Branch', location='Test')
        self.staff = User.objects.create_user(
            username='initiation_staff',
            phone_number='+254711300999',
            role=User.Role.STAFF,
            branch=self.branch,
        )
        self.order = Order.objects.create(
            branch=self.branch,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254711301000',
            subtotal=Decimal('900.00'),
            total_payable=Decimal('900.00'),
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.staff,
            status=Order.Status.PENDING,
        )

    @patch.dict(os.environ, {
        'MPESA_SHORTCODE': '174379',
        'MPESA_PASSKEY': 'test-passkey',
        'MPESA_CALLBACK_URL': 'https://example.test/payments/mpesa/callback/',
    })
    @patch('payments.services.MpesaDarajaService.generate_access_token', return_value='token')
    @patch('payments.services.requests.post')
    def test_failed_initiation_is_recorded_and_can_be_retried_safely(
        self, mock_post, _mock_token,
    ):
        mock_post.side_effect = requests.RequestException('provider unavailable')
        with self.assertRaises(ValidationError):
            MpesaDarajaService.initiate_stk_push(self.order, '+254711301000')
        payment = MpesaTransaction.objects.get(order=self.order)
        self.assertEqual(payment.status, MpesaTransaction.Status.INITIATION_FAILED)
        self.assertEqual(payment.initiation_attempts, 1)

        response = Mock(status_code=200)
        response.json.return_value = {
            'ResponseCode': '0',
            'MerchantRequestID': 'RETRY-MERCHANT',
            'CheckoutRequestID': 'RETRY-CHECKOUT',
        }
        mock_post.side_effect = None
        mock_post.return_value = response
        with patch('payments.tasks.poll_pending_stk_push_status.apply_async'):
            retried = MpesaDarajaService.initiate_stk_push(
                self.order,
                '+254711301000',
            )
        self.assertEqual(retried.pk, payment.pk)
        self.assertEqual(retried.status, MpesaTransaction.Status.PENDING)
        self.assertEqual(retried.initiation_attempts, 2)

    @patch.dict(os.environ, {
        'MPESA_SHORTCODE': '174379',
        'MPESA_PASSKEY': 'test-passkey',
        'MPESA_CALLBACK_URL': 'https://example.test/payments/mpesa/callback/',
    })
    @patch('payments.services.MpesaDarajaService.generate_access_token', return_value='token')
    @patch('payments.services.requests.post')
    def test_repeated_request_does_not_send_a_second_stk_prompt(
        self, mock_post, _mock_token,
    ):
        response = Mock(status_code=200)
        response.json.return_value = {
            'ResponseCode': '0',
            'MerchantRequestID': 'ONE-MERCHANT',
            'CheckoutRequestID': 'ONE-CHECKOUT',
        }
        mock_post.return_value = response
        with patch('payments.tasks.poll_pending_stk_push_status.apply_async'):
            first = MpesaDarajaService.initiate_stk_push(self.order, '+254711301000')
            second = MpesaDarajaService.initiate_stk_push(self.order, '+254711301000')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(mock_post.call_count, 1)


class MpesaCallbackWebhookProcessingTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.branch = Branch.objects.create(name="Mombasa Core", location="Nyali")
        self.cashier = User.objects.create_user(username="clerk_one", phone_number="+254700111222")
        
        self.category = Category.objects.create(name="Hardware")
        self.product = Product.objects.create(name="Cement", category=self.category, price=Decimal('900.00'))
        self.variant = ProductVariant.objects.create(product=self.product, attribute_name="Weight", attribute_value="50KG")

        # Set up a target base order record
        self.order = Order.objects.create(
            branch=self.branch,
            customer_phone="+254712345678",
            subtotal=Decimal('900.00'),
            total_payable=Decimal('900.00'),
            order_type=Order.OrderType.ONLINE_DELIVERY,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.cashier,
            status=Order.Status.PENDING
        )

        # Pre-seed our pending request transaction reference row mock
        self.tracking_tx = MpesaTransaction.objects.create(
            order=self.order,
            merchant_request_id="MOCK_MERCHANT_ID_123",
            checkout_request_id="ws_CO_14062026_XYZ_789",
            status=MpesaTransaction.Status.PENDING
        )

    def test_successful_mpesa_callback_updates_order_state(self):
        """A paid online order advances into fulfilment, not directly to completion."""
        OrderItem.objects.create(
            order=self.order, variant=self.variant, quantity=1,
            unit_price=Decimal('900.00'),
        )
        stock = Stock.objects.create(
            branch=self.branch, variant=self.variant,
            quantity=5, reserved_quantity=1,
        )
        success_payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "MOCK_MERCHANT_ID_123",
                    "CheckoutRequestID": "ws_CO_14062026_XYZ_789",
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 900.00},
                            {"Name": "MpesaReceiptNumber", "Value": "RFI67T89QX"},
                            {"Name": "PhoneNumber", "Value": 254712345678}
                        ]
                    }
                }
            }
        }

        url = reverse('payments:mpesa_callback')
        response = self.client.post(
            url, 
            data=json.dumps(success_payload), 
            content_type='application/json'
        )
        duplicate_response = self.client.post(
            url,
            data=json.dumps(success_payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(duplicate_response.status_code, 200)
        webhook_event = MpesaWebhookEvent.objects.get()
        self.assertEqual(webhook_event.delivery_count, 2)
        self.assertEqual(
            webhook_event.processing_status,
            MpesaWebhookEvent.ProcessingStatus.PROCESSED,
        )
        
        # Verify transaction state transitioned safely to SUCCESS
        self.tracking_tx.refresh_from_db()
        self.assertEqual(self.tracking_tx.status, MpesaTransaction.Status.SUCCESS)
        self.assertEqual(self.tracking_tx.mpesa_receipt_number, "RFI67T89QX")

        # Payment starts fulfilment; delivery or collection completes the order later.
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertEqual(self.order.payment_reference, "RFI67T89QX")
        self.assertTrue(OrderStatusHistory.objects.filter(
            order=self.order,
            old_status=Order.Status.PENDING,
            new_status=Order.Status.PROCESSING,
        ).exists())
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 4)
        self.assertEqual(stock.reserved_quantity, 0)
        self.assertEqual(StockAuditLog.objects.filter(
            reference_number=self.order.order_number,
            reason=StockAuditLog.Reason.RESERVATION_CONSUMED,
        ).count(), 1)

    def test_amount_mismatch_does_not_confirm_order(self):
        payload = {
            'Body': {
                'stkCallback': {
                    'MerchantRequestID': self.tracking_tx.merchant_request_id,
                    'CheckoutRequestID': self.tracking_tx.checkout_request_id,
                    'ResultCode': 0,
                    'ResultDesc': 'Success',
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'Amount', 'Value': 800.00},
                            {'Name': 'MpesaReceiptNumber', 'Value': 'UNDERPAID001'},
                            {'Name': 'PhoneNumber', 'Value': 254712345678},
                        ],
                    },
                },
            },
        }

        response = self.client.post(
            reverse('payments:mpesa_callback'),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.tracking_tx.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(
            self.tracking_tx.status,
            MpesaTransaction.Status.RECONCILIATION_REQUIRED,
        )
        self.assertEqual(
            MpesaWebhookEvent.objects.get().processing_status,
            MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
        )
        self.assertIn('Amount mismatch', self.tracking_tx.failure_reason)
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertIsNone(self.order.payment_reference)

    def test_success_without_amount_or_receipt_requires_reconciliation(self):
        payload = {
            'Body': {'stkCallback': {
                'MerchantRequestID': self.tracking_tx.merchant_request_id,
                'CheckoutRequestID': self.tracking_tx.checkout_request_id,
                'ResultCode': 0,
                'ResultDesc': 'Success without financial evidence',
            }},
        }
        self.client.post(
            reverse('payments:mpesa_callback'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.tracking_tx.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(
            self.tracking_tx.status,
            MpesaTransaction.Status.RECONCILIATION_REQUIRED,
        )
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_merchant_request_mismatch_never_confirms(self):
        payload = {
            'Body': {'stkCallback': {
                'MerchantRequestID': 'WRONG-MERCHANT',
                'CheckoutRequestID': self.tracking_tx.checkout_request_id,
                'ResultCode': 0,
                'ResultDesc': 'Success',
                'CallbackMetadata': {'Item': [
                    {'Name': 'Amount', 'Value': 900},
                    {'Name': 'MpesaReceiptNumber', 'Value': 'MISMATCH001'},
                ]},
            }},
        }
        self.client.post(
            reverse('payments:mpesa_callback'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.tracking_tx.refresh_from_db()
        self.assertEqual(
            self.tracking_tx.status,
            MpesaTransaction.Status.RECONCILIATION_REQUIRED,
        )
        self.assertIsNone(self.tracking_tx.mpesa_receipt_number)
        self.assertEqual(
            MpesaWebhookEvent.objects.get().outcome,
            'identifier_mismatch',
        )

    def test_terminal_failure_restores_stock_once(self):
        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            quantity=1,
            unit_price=Decimal('900.00'),
        )
        stock = Stock.objects.create(
            branch=self.branch,
            variant=self.variant,
            quantity=5,
            reserved_quantity=1,
        )
        payload = {
            'Body': {
                'stkCallback': {
                    'MerchantRequestID': self.tracking_tx.merchant_request_id,
                    'CheckoutRequestID': self.tracking_tx.checkout_request_id,
                    'ResultCode': 1032,
                    'ResultDesc': 'Request cancelled by user',
                },
            },
        }
        url = reverse('payments:mpesa_callback')

        first = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        second = self.client.post(url, data=json.dumps(payload), content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.tracking_tx.refresh_from_db()
        self.order.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(self.tracking_tx.status, MpesaTransaction.Status.FAILED)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(stock.quantity, 5)
        self.assertEqual(stock.reserved_quantity, 0)
        self.assertEqual(StockAuditLog.objects.filter(
            reference_number=self.order.order_number,
            reason=StockAuditLog.Reason.RESERVATION_RELEASE,
        ).count(), 1)

    def test_missing_transaction_context_is_acknowledged_without_mutation(self):
        """Unknown callbacks are logged and acknowledged to prevent endless provider retries."""
        ghost_payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "UNKNOWN_ID",
                    "CheckoutRequestID": "GHOST_CHECKOUT_ID_999", # Non-existent reference
                    "ResultCode": 0,
                    "ResultDesc": "Success payload on unmapped record."
                }
            }
        }

        url = reverse('payments:mpesa_callback')
        response = self.client.post(
            url, 
            data=json.dumps(ghost_payload), 
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content.decode())
        self.assertEqual(response_data['ResultCode'], 0)
        self.assertEqual(response_data['ResultDesc'], 'Accepted.')
        self.assertEqual(MpesaTransaction.objects.count(), 1)
        event = MpesaWebhookEvent.objects.get()
        self.assertEqual(event.outcome, 'unknown_checkout_request')
        self.assertEqual(
            event.processing_status,
            MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
        )

    def test_malformed_callback_is_durably_retained_without_raw_payload(self):
        response = self.client.post(
            reverse('payments:mpesa_callback'),
            data=b'{invalid-json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        event = MpesaWebhookEvent.objects.get()
        self.assertEqual(event.outcome, 'malformed_payload')
        self.assertEqual(event.sanitized_evidence, {'payload_size': 13})
        self.assertFalse(hasattr(event, 'raw_payload'))

    @patch('payments.views._record_webhook_delivery')
    def test_callback_returns_retryable_error_when_durable_inbox_is_unavailable(
        self, mock_record,
    ):
        from django.db import DatabaseError

        mock_record.side_effect = DatabaseError('database unavailable')
        response = self.client.post(
            reverse('payments:mpesa_callback'),
            data=json.dumps({'Body': {'stkCallback': {}}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 503)

    def test_manual_confirmation_requires_manager_reauth_and_creates_risk_audit(self):
        self.cashier.role = User.Role.STAFF
        self.cashier.branch = self.branch
        self.cashier.save(update_fields=['role', 'branch'])
        manager = User.objects.create_user(
            username='payment_manager',
            phone_number='+254711000999',
            email='payment.manager@test.invalid',
            password='ManagerPaymentPass123!',
            role=User.Role.BRANCH_MANAGER,
            branch=self.branch,
        )
        self.tracking_tx.expected_amount = self.order.total_payable
        self.tracking_tx.submitted_reference = 'MANUAL900X'
        self.tracking_tx.status = MpesaTransaction.Status.RECONCILIATION_REQUIRED
        self.tracking_tx.save(update_fields=[
            'expected_amount', 'submitted_reference', 'status',
        ])
        review_event = MpesaWebhookEvent.objects.create(
            payload_sha256='a' * 64,
            payload_size=100,
            payment=self.tracking_tx,
            processing_status=MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
            outcome='reconciliation_required',
        )
        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            quantity=1,
            unit_price=Decimal('900.00'),
        )
        Stock.objects.create(
            branch=self.branch,
            variant=self.variant,
            quantity=5,
            reserved_quantity=1,
        )
        self.client.force_login(self.cashier)
        response = self.client.post(
            reverse('payments:mpesa_manual_confirm', args=[self.tracking_tx.pk]),
            data=json.dumps({
                'manager_username': manager.username,
                'manager_password': 'ManagerPaymentPass123!',
                'amount': '900.00',
                'receipt_number': 'MANUAL900X',
                'reason': 'Verified against the authorized M-Pesa transaction statement.',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.tracking_tx.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.tracking_tx.status, MpesaTransaction.Status.SUCCESS)
        self.assertEqual(
            self.tracking_tx.confirmation_method,
            MpesaTransaction.ConfirmationMethod.MANUAL_STAFF,
        )
        self.assertEqual(self.tracking_tx.confirmed_by, manager)
        self.assertEqual(self.order.status, Order.Status.PROCESSING)
        self.assertTrue(OperationalAuditRiskLog.objects.filter(
            action_type='MANUAL_MPESA_MATCH',
            target_record_id=str(self.tracking_tx.pk),
            initiator=manager,
        ).exists())
        review_event.refresh_from_db()
        self.assertEqual(
            review_event.processing_status,
            MpesaWebhookEvent.ProcessingStatus.RESOLVED,
        )
        self.assertEqual(review_event.resolved_by, manager)

    def test_super_admin_can_audit_and_resolve_unmatched_webhook_event(self):
        super_admin = User.objects.create_superuser(
            username='webhook_super_admin',
            phone_number='+254711001111',
            email='webhook.admin@test.invalid',
            password='WebhookAdminPass123!',
        )
        event = MpesaWebhookEvent.objects.create(
            payload_sha256='b' * 64,
            payload_size=25,
            processing_status=MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
            outcome='unknown_checkout_request',
            review_reason='No payment matched.',
        )
        self.client.force_login(super_admin)
        response = self.client.post(
            reverse('payments:mpesa_webhook_event_resolve', args=[event.pk]),
            data=json.dumps({
                'manager_username': super_admin.username,
                'manager_password': 'WebhookAdminPass123!',
                'resolution_note': 'Confirmed as a sandbox callback for an expired test request.',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(
            event.processing_status,
            MpesaWebhookEvent.ProcessingStatus.RESOLVED,
        )
        self.assertEqual(event.resolved_by, super_admin)
        self.assertTrue(OperationalAuditRiskLog.objects.filter(
            action_type='MPESA_WEBHOOK_REVIEW',
            target_record_id=str(event.pk),
        ).exists())
