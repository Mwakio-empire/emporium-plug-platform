
import logging
from celery import shared_task
logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 120
MAX_POLL_ATTEMPTS = 15  # 15 * 2min = 30min ceiling
# Terminal failure codes -- no point continuing to poll these.
# 1032=cancelled by user, 1=insufficient funds, 1037=timeout, 1025/2001=generic failures.
_TERMINAL_FAILURE_CODES = ('1032', '1', '1037', '1025', '2001')
def _attempt_stk_poll(mpesa_transaction_id):
    """
    Single poll attempt -- pure, no Celery retry machinery, directly
    unit-testable. Returns one of:
      'not_found', 'already_resolved', 'confirmed', 'failed', 'still_pending'
    """
    from .models import MpesaTransaction
    from .services import MpesaDarajaService, PaymentSettlementService
    from django.core.exceptions import ValidationError
    try:
        txn = MpesaTransaction.objects.select_related('order').get(id=mpesa_transaction_id)
    except MpesaTransaction.DoesNotExist:
        logger.warning(f"_attempt_stk_poll: transaction {mpesa_transaction_id} not found.")
        return 'not_found'
    if txn.status != MpesaTransaction.Status.PENDING:
        return 'already_resolved'
    try:
        result = MpesaDarajaService.query_stk_push_status(txn.checkout_request_id)
    except ValidationError:
        logger.warning("STK query failed for payment id=%s.", mpesa_transaction_id)
        return 'still_pending'
    result_code = str(result.get('ResultCode', ''))
    if result_code == '0':
        outcome = PaymentSettlementService.mark_query_confirmed(
            mpesa_transaction_id,
            description=result.get('ResultDesc', ''),
        )
        if outcome == 'already_resolved':
            return outcome
        logger.warning(
            "STK query reports success but receipt evidence is pending | PaymentID=%s",
            mpesa_transaction_id,
        )
        return 'query_confirmed'
    elif result_code in _TERMINAL_FAILURE_CODES:
        outcome = PaymentSettlementService.fail(
            mpesa_transaction_id,
            reason=result.get('ResultDesc', 'Payment not completed.'),
        )
        if outcome == 'already_resolved':
            return outcome
        logger.info(f"STK poll: transaction {mpesa_transaction_id} definitively failed ({result_code}).")
        return 'failed'
    return 'still_pending'
@shared_task(bind=True, max_retries=MAX_POLL_ATTEMPTS, name='payments.poll_pending_stk_push_status')
def poll_pending_stk_push_status(self, mpesa_transaction_id):
    """
    Daraja callback retry queue (§9 Scenario 2). Polls every 2 minutes for
    up to 30 minutes when the async webhook callback never arrives.
    """
    outcome = _attempt_stk_poll(mpesa_transaction_id)
    if outcome in ('query_confirmed', 'failed', 'already_resolved', 'not_found'):
        return outcome
    if self.request.retries >= MAX_POLL_ATTEMPTS - 1:
        logger.warning(
            f"STK poll exhausted after {MAX_POLL_ATTEMPTS} attempts for "
            f"transaction {mpesa_transaction_id} -- left PENDING for manual/fallback confirmation."
        )
        return 'exhausted'
    raise self.retry(countdown=POLL_INTERVAL_SECONDS)
