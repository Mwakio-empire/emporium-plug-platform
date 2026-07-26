from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from branches.models import Branch
from orders.models import Order
from payments.models import MpesaTransaction
from payments.tasks import _attempt_stk_poll
from payments.services import PaymentSettlementService
User = get_user_model()
class StkPollAttemptTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Poll Test Branch", location="Test")
        self.customer = User.objects.create_user(
            username='pollcust0001', phone_number='+254788600001',
            email='pollcust0001@test.com', password='CustPass123!',
            role=User.Role.CUSTOMER,
        )
        self.order = Order.objects.create(
            branch=self.branch, customer=self.customer,
            order_type=Order.OrderType.ONLINE_PICKUP,
            customer_phone='+254788600001',
            payment_method=Order.PaymentMethod.MPESA_STK,
            status=Order.Status.PENDING,
            processed_by=self.customer,
            subtotal=Decimal('1000.00'), total_payable=Decimal('1000.00'),
        )
        self.txn = MpesaTransaction.objects.create(
            order=self.order,
            merchant_request_id='POLL_MERCHANT_1',
            checkout_request_id='POLL_CHECKOUT_1',
            status=MpesaTransaction.Status.PENDING,
        )
    def test_not_found_returns_not_found(self):
        self.assertEqual(_attempt_stk_poll(999999), 'not_found')
    def test_already_success_returns_already_resolved(self):
        self.txn.status = MpesaTransaction.Status.SUCCESS
        self.txn.save(update_fields=['status'])
        self.assertEqual(_attempt_stk_poll(self.txn.id), 'already_resolved')
    @patch('payments.services.MpesaDarajaService.query_stk_push_status')
    def test_result_code_zero_records_query_evidence_without_settling(self, mock_query):
        mock_query.return_value = {'ResultCode': '0', 'ResultDesc': 'Success'}
        result = _attempt_stk_poll(self.txn.id)
        self.assertEqual(result, 'query_confirmed')
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, MpesaTransaction.Status.QUERY_CONFIRMED)
        self.assertIsNotNone(self.txn.query_confirmed_at)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
    @patch('payments.services.MpesaDarajaService.query_stk_push_status')
    def test_terminal_failure_code_marks_failed(self, mock_query):
        mock_query.return_value = {'ResultCode': '1032', 'ResultDesc': 'Request cancelled by user'}
        result = _attempt_stk_poll(self.txn.id)
        self.assertEqual(result, 'failed')
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, MpesaTransaction.Status.FAILED)
        self.assertIn('cancelled', self.txn.failure_reason)
    @patch('payments.services.MpesaDarajaService.query_stk_push_status')
    def test_indeterminate_result_stays_pending(self, mock_query):
        mock_query.return_value = {'ResultCode': '500.001.1001', 'ResultDesc': 'still processing'}
        result = _attempt_stk_poll(self.txn.id)
        self.assertEqual(result, 'still_pending')
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, MpesaTransaction.Status.PENDING)
    @patch('payments.services.MpesaDarajaService.query_stk_push_status')
    def test_query_exception_returns_still_pending(self, mock_query):
        mock_query.side_effect = ValidationError("Gateway timeout")
        self.assertEqual(_attempt_stk_poll(self.txn.id), 'still_pending')
    @patch('payments.services.MpesaDarajaService.query_stk_push_status')
    def test_double_confirmation_race_with_webhook_is_idempotent(self, mock_query):
        """Webhook confirms concurrently, right after query returns -- poll must not double-process."""
        def side_effect(checkout_request_id):
            MpesaTransaction.objects.filter(id=self.txn.id).update(status=MpesaTransaction.Status.SUCCESS)
            return {'ResultCode': '0', 'ResultDesc': 'Success'}
        mock_query.side_effect = side_effect
        self.assertEqual(_attempt_stk_poll(self.txn.id), 'already_resolved')

    def test_late_callback_can_settle_query_confirmed_payment(self):
        PaymentSettlementService.mark_query_confirmed(self.txn.id, description='Success')
        outcome = PaymentSettlementService.confirm(
            self.txn.id,
            amount='1000.00',
            receipt_number='LATECALLBACK1',
        )
        self.assertEqual(outcome, 'confirmed')
        self.txn.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.txn.status, MpesaTransaction.Status.SUCCESS)
        self.assertEqual(self.order.status, Order.Status.PROCESSING)

    def test_conflicting_query_success_and_failure_callback_requires_review(self):
        PaymentSettlementService.mark_query_confirmed(self.txn.id, description='Success')
        outcome = PaymentSettlementService.fail(
            self.txn.id,
            reason='Provider callback later reported failure.',
        )
        self.assertEqual(outcome, 'reconciliation_required')
        self.txn.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(
            self.txn.status,
            MpesaTransaction.Status.RECONCILIATION_REQUIRED,
        )
        self.assertEqual(self.order.status, Order.Status.PENDING)
