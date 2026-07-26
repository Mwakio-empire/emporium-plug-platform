import hmac
import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
logger = logging.getLogger(__name__)


class NotificationOperationsView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'notifications/operations.html'

    def test_func(self):
        from users.models import User
        return self.request.user.is_active and self.request.user.role in {
            User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN,
        }

    def _queryset(self):
        from notifications.models import Notification
        from users.models import User
        queryset = Notification.objects.select_related(
            'branch', 'followup_resolved_by',
        ).prefetch_related('delivery_attempts')
        if self.request.user.role == User.Role.BRANCH_MANAGER:
            queryset = queryset.filter(branch=self.request.user.branch)
        return queryset

    def get(self, request):
        queryset = self._queryset()
        return render(request, self.template_name, {
            'followups': queryset.filter(status='MANUAL_FOLLOWUP')[:100],
            'recent': queryset.exclude(status='MANUAL_FOLLOWUP')[:100],
        })

    def post(self, request):
        from notifications.models import Notification
        notification = get_object_or_404(
            self._queryset(), pk=request.POST.get('notification_id'),
            status=Notification.Status.MANUAL_FOLLOWUP,
        )
        note = request.POST.get('resolution_note', '').strip()
        if len(note) < 8:
            messages.error(request, 'Record at least eight characters describing the follow-up evidence.')
            return redirect('notifications:operations')
        with transaction.atomic():
            notification = Notification.objects.select_for_update().get(pk=notification.pk)
            if notification.status != Notification.Status.MANUAL_FOLLOWUP:
                raise PermissionDenied('This notification no longer requires follow-up.')
            notification.status = Notification.Status.RESOLVED_MANUAL
            notification.followup_resolved_at = timezone.now()
            notification.followup_resolved_by = request.user
            notification.followup_resolution_note = note
            notification.save(update_fields=[
                'status', 'followup_resolved_at', 'followup_resolved_by',
                'followup_resolution_note', 'updated_at',
            ])
        messages.success(request, 'Manual notification follow-up recorded.')
        return redirect('notifications:operations')

@csrf_exempt
@require_POST
def sms_inbound_webhook(request):
    """
    Africa's Talking inbound SMS callback — handles the "Reply YES to
    confirm receipt" flow (Business Context §8 Customer Delivery
    Confirmation / §11 collusion-fraud control).
    CRITICAL: must always return 200 -- Africa's Talking retries on
    non-200. All failures are logged internally, never surfaced.
    """
    if not settings.INBOUND_SMS_ENABLED:
        return HttpResponse(status=404)
    supplied_token = (
        request.headers.get('X-Webhook-Token', '')
        or request.GET.get('token', '')
    )
    if not hmac.compare_digest(supplied_token, settings.INBOUND_SMS_WEBHOOK_TOKEN):
        logger.warning('Rejected unauthenticated inbound SMS callback.')
        return HttpResponse(status=404)
    try:
        content_length = int(request.META.get('CONTENT_LENGTH') or 0)
    except (TypeError, ValueError):
        content_length = 0
    if content_length > 16 * 1024:
        logger.warning('Rejected oversized inbound SMS callback.')
        return HttpResponse(status=413)

    sender_phone = request.POST.get('from', '').strip()
    message_text = request.POST.get('text', '').strip()
    if not sender_phone:
        logger.warning("Inbound SMS webhook: missing 'from' field.")
        return HttpResponse(status=200)
    normalized_phone = sender_phone
    if normalized_phone.startswith('0'):
        normalized_phone = '+254' + normalized_phone[1:]
    elif not normalized_phone.startswith('+'):
        normalized_phone = '+' + normalized_phone
    try:
        from logistics.models import DeliveryAssignment
        cutoff = timezone.now() - timedelta(days=7)
        candidate = DeliveryAssignment.objects.filter(
            order__customer_phone__in=[sender_phone, normalized_phone],
            status=DeliveryAssignment.DeliveryStatus.DELIVERED,
            customer_confirmed_at__isnull=True,
            customer_disputed=False,
            completed_at__gte=cutoff,
        ).select_related('order').order_by('-completed_at').first()
        if not candidate:
            logger.info("Inbound SMS had no matching pending delivery confirmation.")
            return HttpResponse(status=200)
        from orders.models import Order
        from orders.transitions import OrderTransitionService
        from users.models import User
        with transaction.atomic():
            candidate = DeliveryAssignment.objects.select_for_update().select_related('order').get(
                pk=candidate.pk,
            )
            actor = candidate.order.customer or candidate.order.processed_by or User.get_system_account()
            if message_text.strip().upper().startswith('YES'):
                candidate.customer_confirmed_at = timezone.now()
                candidate.save(update_fields=['customer_confirmed_at'])
                OrderTransitionService.transition(
                    order=candidate.order, to_status=Order.Status.CUSTOMER_CONFIRMED,
                    changed_by=actor, note='Customer confirmed delivery by SMS.',
                )
                logger.info("Delivery confirmed by customer SMS | OrderID=%s", candidate.order_id)
            else:
                candidate.customer_disputed = True
                candidate.dispute_note = message_text[:500]
                candidate.save(update_fields=['customer_disputed', 'dispute_note'])
                OrderTransitionService.transition(
                    order=candidate.order, to_status=Order.Status.DISPUTED,
                    changed_by=actor, note='Customer disputed delivery by SMS.',
                )
                logger.warning(
                    "Delivery disputed by customer SMS | OrderID=%s",
                    candidate.order_id,
                )
                from notifications.tasks import send_delivery_dispute_manager_alert
                order_id = str(candidate.order.id)
                dispute_text = message_text[:500]
        if candidate.customer_disputed:
            try:
                send_delivery_dispute_manager_alert.delay(order_id, dispute_text)
            except Exception as exc:
                logger.error(
                    'Delivery dispute alert could not be queued | OrderID=%s | ExceptionType=%s',
                    order_id, type(exc).__name__,
                )
    except Exception as exc:
        logger.error(
            "Inbound SMS webhook failed | ExceptionType=%s",
            type(exc).__name__,
        )
    return HttpResponse(status=200)
