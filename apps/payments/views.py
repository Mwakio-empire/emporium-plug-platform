import json
import logging
import hashlib

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MpesaTransaction, MpesaWebhookEvent
from .services import (
    ManualPaymentConfirmationService,
    PaymentSettlementService,
    WebhookEventReviewService,
)


logger = logging.getLogger(__name__)
MAX_CALLBACK_BYTES = 64 * 1024


def _record_webhook_delivery(raw_body):
    digest = hashlib.sha256(raw_body).hexdigest()
    try:
        with transaction.atomic():
            event = MpesaWebhookEvent.objects.create(
                payload_sha256=digest,
                payload_size=len(raw_body),
            )
        return event
    except IntegrityError:
        MpesaWebhookEvent.objects.filter(payload_sha256=digest).update(
            delivery_count=F('delivery_count') + 1,
        )
        return MpesaWebhookEvent.objects.get(payload_sha256=digest)


@csrf_exempt
@require_POST
def mpesa_callback_webhook(request):
    """Acknowledge Daraja callbacks after applying an idempotent outcome."""
    raw_body = request.body
    try:
        event = _record_webhook_delivery(raw_body)
    except DatabaseError as exc:
        logger.critical(
            'Daraja callback inbox unavailable | ExceptionType=%s',
            type(exc).__name__,
        )
        return JsonResponse(
            {'ResultCode': 1, 'ResultDesc': 'Temporary processing failure.'},
            status=503,
        )

    if len(raw_body) > MAX_CALLBACK_BYTES:
        event.mark(
            status=MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
            outcome='payload_too_large',
            reason='Callback exceeded the accepted 64 KiB size limit.',
            evidence={'payload_size': len(raw_body)},
        )
        logger.error('Oversized Daraja callback retained for review | EventID=%s', event.pk)
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted.'})

    try:
        raw_payload = json.loads(raw_body.decode('utf-8'))
        callback = raw_payload['Body']['stkCallback']
        checkout_request_id = callback.get('CheckoutRequestID')
        merchant_request_id = callback.get('MerchantRequestID')
        result_code = callback.get('ResultCode')
        result_description = callback.get('ResultDesc', '')

        event.checkout_request_id = str(checkout_request_id or '')
        event.merchant_request_id = str(merchant_request_id or '')
        event.result_code = str(result_code if result_code is not None else '')
        event.save(update_fields=[
            'checkout_request_id', 'merchant_request_id', 'result_code', 'last_received_at',
        ])

        logger.info(
            'Daraja callback received | ResultCode=%s',
            result_code,
        )

        try:
            payment = MpesaTransaction.objects.select_related('order').get(
                checkout_request_id=checkout_request_id,
            )
        except MpesaTransaction.DoesNotExist:
            event.mark(
                status=MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
                outcome='unknown_checkout_request',
                reason='No local payment matched the callback checkout request identifier.',
                evidence={
                    'checkout_request_id': checkout_request_id,
                    'result_code': result_code,
                },
            )
            logger.warning(
                'Daraja callback for unknown checkout request retained for review | EventID=%s',
                event.pk,
            )
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted.'})

        if not merchant_request_id or merchant_request_id != payment.merchant_request_id:
            payment.status = MpesaTransaction.Status.RECONCILIATION_REQUIRED
            payment.failure_reason = 'Callback merchant request identifier did not match initiation.'
            payment.raw_callback_payload = {
                'result_code': result_code,
                'checkout_request_id': checkout_request_id,
                'merchant_request_id_matched': False,
            }
            payment.save(update_fields=[
                'status', 'failure_reason', 'raw_callback_payload', 'updated_at',
            ])
            event.mark(
                status=MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
                outcome='identifier_mismatch',
                reason='Merchant request identifier did not match the local initiation.',
                evidence=payment.raw_callback_payload,
                payment=payment,
            )
            logger.error('M-Pesa callback identifier mismatch | PaymentID=%s', payment.pk)
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted.'})

        sanitized_evidence = {
            'result_code': result_code,
            'result_description': result_description,
            'checkout_request_id': checkout_request_id,
            'merchant_request_id_matched': True,
        }

        if result_code == 0:
            metadata = {
                item['Name']: item.get('Value')
                for item in callback.get('CallbackMetadata', {}).get('Item', [])
            }
            outcome = PaymentSettlementService.confirm(
                payment.id,
                amount=metadata.get('Amount'),
                receipt_number=metadata.get('MpesaReceiptNumber'),
                raw_callback_payload=sanitized_evidence,
            )

            if outcome == 'reconciliation_required':
                event.mark(
                    status=MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
                    outcome=outcome,
                    reason='Callback financial evidence requires manual reconciliation.',
                    evidence=sanitized_evidence,
                    payment=payment,
                )
                logger.error(
                    'M-Pesa payment requires reconciliation | PaymentID=%s',
                    payment.pk,
                )
            elif outcome == 'confirmed':
                event.mark(
                    status=MpesaWebhookEvent.ProcessingStatus.PROCESSED,
                    outcome=outcome,
                    evidence=sanitized_evidence,
                    payment=payment,
                )
                logger.info('M-Pesa payment confirmed | PaymentID=%s', payment.pk)
                try:
                    from notifications.tasks import send_payment_confirmed_sms
                    send_payment_confirmed_sms.delay(str(payment.order_id))
                except Exception as exc:
                    logger.error(
                        'Payment confirmed but SMS could not be queued | PaymentID=%s | ExceptionType=%s',
                        payment.pk,
                        type(exc).__name__,
                    )
            else:
                event.mark(
                    status=MpesaWebhookEvent.ProcessingStatus.PROCESSED,
                    outcome=outcome,
                    evidence=sanitized_evidence,
                    payment=payment,
                )
                logger.info('Duplicate M-Pesa callback ignored | PaymentID=%s', payment.pk)
        else:
            outcome = PaymentSettlementService.fail(
                payment.id,
                reason=result_description or 'Payment not completed.',
                raw_callback_payload=sanitized_evidence,
            )
            event.mark(
                status=(
                    MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED
                    if outcome == 'reconciliation_required'
                    else MpesaWebhookEvent.ProcessingStatus.PROCESSED
                ),
                outcome=outcome,
                reason=(
                    'Provider result conflicted with existing success evidence.'
                    if outcome == 'reconciliation_required'
                    else ''
                ),
                evidence=sanitized_evidence,
                payment=payment,
            )
            logger.warning(
                'M-Pesa payment failure | PaymentID=%s | Outcome=%s',
                payment.pk,
                outcome,
            )

    except (ValueError, UnicodeDecodeError, KeyError, TypeError):
        event.mark(
            status=MpesaWebhookEvent.ProcessingStatus.REVIEW_REQUIRED,
            outcome='malformed_payload',
            reason='Callback was not valid expected Daraja JSON.',
            evidence={'payload_size': len(raw_body)},
        )
        logger.error('Malformed Daraja callback retained for review | EventID=%s', event.pk)
    except Exception as exc:
        # Provider callbacks are acknowledged to avoid an unbounded retry storm.
        # The exception remains visible to monitoring for manual reconciliation.
        logger.error(
            'Unexpected Daraja callback failure | EventID=%s | ExceptionType=%s',
            event.pk,
            type(exc).__name__,
        )
        event.mark(
            status=MpesaWebhookEvent.ProcessingStatus.PROCESSING_FAILED,
            outcome='unexpected_processing_failure',
            reason=f'Unexpected callback processing failure: {type(exc).__name__}.',
            evidence={'payload_size': len(raw_body)},
        )

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted.'})


class ManualPaymentConfirmationView(APIView):
    """Internal manager-authorized reconciliation; never customer accessible."""

    permission_classes = [IsAuthenticated]

    def post(self, request, payment_id):
        try:
            payment = ManualPaymentConfirmationService.confirm(
                payment_id=payment_id,
                requesting_staff=request.user,
                manager_username=request.data.get('manager_username'),
                manager_password=request.data.get('manager_password'),
                amount=request.data.get('amount'),
                receipt_number=request.data.get('receipt_number'),
                reason=request.data.get('reason'),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'payment_id': payment.pk,
            'status': payment.status,
            'order_number': payment.order.order_number,
        })


class WebhookEventResolveView(APIView):
    """Audited operational closure for durable callback-inbox items."""

    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        try:
            event = WebhookEventReviewService.resolve(
                event_id=event_id,
                requesting_staff=request.user,
                manager_username=request.data.get('manager_username'),
                manager_password=request.data.get('manager_password'),
                resolution_note=request.data.get('resolution_note'),
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'event_id': event.pk,
            'status': event.processing_status,
        })
