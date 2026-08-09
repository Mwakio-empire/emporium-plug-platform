import logging
from collections import defaultdict

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from users.models import User

from .models import LowStockAlertState, Stock


logger = logging.getLogger(__name__)


def _stock_item(stock):
    return stock.variant or stock.product


def _threshold(stock):
    product = stock.variant.product if stock.variant_id else stock.product
    return product.low_stock_threshold


@shared_task(name='inventory.send_branch_low_stock_alerts')
def send_branch_low_stock_alerts():
    """Send once when a branch stock row crosses into a low-stock state."""

    transitions = defaultdict(list)
    now = timezone.now()
    with transaction.atomic():
        stocks = list(Stock.objects.select_for_update(of=('self',)).select_related(
            'branch', 'product', 'variant__product',
        ))
        for stock in stocks:
            threshold = _threshold(stock)
            if stock.available_quantity <= threshold:
                state, created = LowStockAlertState.objects.select_for_update().get_or_create(
                    stock=stock,
                )
                if created or not state.is_active or state.last_notified_at is None:
                    state.is_active = True
                    state.resolved_at = None
                    state.save(update_fields=['is_active', 'resolved_at'])
                    transitions[stock.branch_id].append((stock, state))
            else:
                LowStockAlertState.objects.filter(
                    stock=stock, is_active=True,
                ).update(is_active=False, resolved_at=now)

    sent = 0
    from notifications.catalog import EventType
    from notifications.tasks import queue_sms_event

    for branch_id, entries in transitions.items():
        branch = entries[0][0].branch
        recipients = User.objects.filter(
            is_active=True,
            role__in=[
                User.Role.INVENTORY_MANAGER,
                User.Role.BRANCH_MANAGER,
                User.Role.SUPER_ADMIN,
            ],
        ).filter(
            Q(branch_id=branch_id) | Q(role=User.Role.SUPER_ADMIN)
        ).exclude(phone_number='').exclude(phone_number__isnull=True).distinct()
        lines = [
            f"{_stock_item(stock)}: {stock.available_quantity} available "
            f"(threshold {_threshold(stock)})"
            for stock, _ in entries[:20]
        ]
        if len(entries) > 20:
            lines.append(f"...and {len(entries) - 20} more item(s).")
        message = f"LOW STOCK - {branch.name}\n" + "\n".join(lines)
        recipient_count = 0
        for recipient in recipients:
            queued = queue_sms_event(
                str(recipient.phone_number), message, EventType.LOW_STOCK,
                'branch', branch_id,
                occurrence=now.isoformat(),
                branch=branch,
            )
            if queued:
                sent += 1
                recipient_count += 1
        if recipient_count:
            LowStockAlertState.objects.filter(
                pk__in=[state.pk for _, state in entries],
            ).update(last_notified_at=now)

    logger.info(
        "Branch low-stock sweep completed | transitions=%s | messages=%s",
        sum(len(entries) for entries in transitions.values()), sent,
    )
    return {'transitions': sum(map(len, transitions.values())), 'messages': sent}
