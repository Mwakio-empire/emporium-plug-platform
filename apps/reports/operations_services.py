from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Avg, Count, DecimalField, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from analytics.models import AuditLog
from inventory.models import Stock, StockAuditLog, TransferRequest
from logistics.models import DeliveryAssignment
from marketing.models import CouponRedemption, ReturnRequest
from orders.models import Order, OrderItem, OrderStatusHistory
from payments.models import MpesaTransaction
from reports.models import ShiftReconciliation


MONEY = Decimal('0.01')


def money(value):
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


class OperationsReportService:
    """Authoritative Phase 10 operational reporting calculations."""

    REVENUE_STATUSES = (
        Order.Status.COMPLETED,
        Order.Status.DELIVERED,
        Order.Status.CUSTOMER_CONFIRMED,
        Order.Status.COLLECTED,
    )
    FAILED_PAYMENT_STATUSES = (
        MpesaTransaction.Status.FAILED,
        MpesaTransaction.Status.INITIATION_FAILED,
        MpesaTransaction.Status.RECONCILIATION_REQUIRED,
    )

    @classmethod
    def date_bounds(cls, start_date, end_date):
        if not start_date or not end_date:
            raise ValueError('Both start and end dates are required.')
        if start_date > end_date:
            raise ValueError('Start date cannot be after end date.')
        if (end_date - start_date).days > 366:
            raise ValueError('Report ranges cannot exceed 366 calendar days.')
        tz = timezone.get_current_timezone()
        start_at = timezone.make_aware(datetime.combine(start_date, time.min), tz)
        end_at = timezone.make_aware(
            datetime.combine(end_date + timedelta(days=1), time.min), tz,
        )
        return start_at, end_at

    @classmethod
    def recognized_orders(cls, *, start_at, end_at, branch=None):
        first_success = OrderStatusHistory.objects.filter(
            order_id=OuterRef('pk'),
            new_status__in=cls.REVENUE_STATUSES,
        ).order_by('created_at').values('created_at')[:1]
        queryset = Order.objects.filter(
            status__in=cls.REVENUE_STATUSES,
        ).annotate(
            recognized_at=Coalesce(
                Subquery(first_success),
                F('created_at'),
            ),
        ).filter(recognized_at__gte=start_at, recognized_at__lt=end_at)
        if branch is not None:
            queryset = queryset.filter(branch=branch)
        return queryset

    @classmethod
    def compile(cls, *, start_date, end_date, branch=None):
        start_at, end_at = cls.date_bounds(start_date, end_date)
        orders = cls.recognized_orders(
            start_at=start_at, end_at=end_at, branch=branch,
        )
        order_ids = orders.values('id')
        sales = orders.aggregate(
            revenue=Coalesce(
                Sum('total_payable'), Decimal('0.00'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            subtotal=Coalesce(
                Sum('subtotal'), Decimal('0.00'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            delivery_fees=Coalesce(
                Sum('delivery_fee'), Decimal('0.00'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            discounts=Coalesce(
                Sum('discount_amount'), Decimal('0.00'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            orders=Count('id'),
            average_order=Avg('total_payable'),
        )

        payment_breakdown = list(orders.values('payment_method').annotate(
            order_count=Count('id'), amount=Sum('total_payable'),
        ).order_by('payment_method'))
        channel_breakdown = list(orders.values('sales_channel').annotate(
            order_count=Count('id'), amount=Sum('total_payable'),
        ).order_by('sales_channel'))
        branch_breakdown = list(orders.values('branch_id', 'branch__name').annotate(
            order_count=Count('id'), amount=Sum('total_payable'),
        ).order_by('-amount', 'branch__name'))
        staff_breakdown = list(orders.filter(
            order_type=Order.OrderType.WALK_IN,
        ).values(
            'processed_by_id', 'processed_by__first_name',
            'processed_by__last_name', 'processed_by__username',
        ).annotate(
            order_count=Count('id'), amount=Sum('total_payable'),
            discounts=Sum('discount_amount'),
        ).order_by('-amount'))

        product_rows = cls._product_performance(order_ids, branch)
        inventory = cls._inventory_summary(branch, product_rows)
        controls = cls._control_summary(start_at, end_at, branch)
        fulfilment = cls._fulfilment_summary(start_at, end_at, branch)
        promotions_returns = cls._promotion_return_summary(start_at, end_at, branch)

        return {
            'definition': {
                'timezone': str(timezone.get_current_timezone()),
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'branch': branch.name if branch else 'All branches',
                'revenue_basis': (
                    'Order total payable when a sale first reaches Completed, Delivered, '
                    'Customer Confirmed, or Collected. Disputed, cancelled, voided, '
                    'returned, pending and processing orders are excluded.'
                ),
                'returns_basis': 'Returns and refund obligations are reported separately; revenue is not silently netted.',
            },
            'sales': {
                'revenue': money(sales['revenue']),
                'subtotal': money(sales['subtotal']),
                'delivery_fees': money(sales['delivery_fees']),
                'discounts': money(sales['discounts']),
                'orders': sales['orders'],
                'average_order': money(sales['average_order']),
                'payment_breakdown': cls._money_rows(payment_breakdown),
                'channel_breakdown': cls._money_rows(channel_breakdown),
                'branch_breakdown': cls._money_rows(branch_breakdown),
                'staff_breakdown': cls._money_rows(staff_breakdown, extra_money=('discounts',)),
            },
            'products': product_rows,
            'inventory': inventory,
            'controls': controls,
            'fulfilment': fulfilment,
            'promotions_returns': promotions_returns,
            'generated_at': timezone.now(),
        }

    @staticmethod
    def _money_rows(rows, extra_money=()):
        normalized = []
        for row in rows:
            row = dict(row)
            row['amount'] = money(row.get('amount'))
            for field in extra_money:
                row[field] = money(row.get(field))
            normalized.append(row)
        return normalized

    @classmethod
    def _product_performance(cls, order_ids, branch):
        lines = OrderItem.objects.filter(order_id__in=order_ids).values(
            'product_id', 'product__name', 'product__sku',
            'variant__product_id', 'variant__product__name', 'variant__product__sku',
        ).annotate(units=Sum('quantity'), amount=Sum('total_price'))
        combined = defaultdict(lambda: {'units': 0, 'amount': Decimal('0.00')})
        for line in lines:
            product_id = line['product_id'] or line['variant__product_id']
            if not product_id:
                continue
            row = combined[product_id]
            row['product_id'] = product_id
            row['name'] = line['product__name'] or line['variant__product__name']
            row['sku'] = line['product__sku'] or line['variant__product__sku']
            row['units'] += line['units'] or 0
            row['amount'] += money(line['amount'])
        return sorted(combined.values(), key=lambda row: (-row['units'], row['name']))

    @classmethod
    def _inventory_summary(cls, branch, product_rows):
        stocks = Stock.objects.all()
        if branch is not None:
            stocks = stocks.filter(branch=branch)
        totals = stocks.aggregate(
            on_hand=Coalesce(Sum('quantity'), 0),
            reserved=Coalesce(Sum('reserved_quantity'), 0),
            in_transit=Coalesce(Sum('in_transit_quantity'), 0),
            damaged=Coalesce(Sum('damaged_quantity'), 0),
            stock_lines=Count('id'),
        )
        totals['available'] = totals['on_hand'] - totals['reserved']
        sold_ids = {row['product_id'] for row in product_rows}
        dead_stock = []
        for stock in stocks.select_related('product', 'variant__product', 'branch'):
            product = stock.product or stock.variant.product
            if stock.available_quantity > 0 and product.pk not in sold_ids:
                dead_stock.append({
                    'product_id': product.pk,
                    'name': product.name,
                    'sku': product.sku,
                    'branch': stock.branch.name,
                    'available': stock.available_quantity,
                })
        totals['slow_or_dead_stock'] = sorted(
            dead_stock, key=lambda row: (-row['available'], row['name']),
        )[:100]
        return totals

    @classmethod
    def _control_summary(cls, start_at, end_at, branch):
        order_filter = Q(created_at__gte=start_at, created_at__lt=end_at)
        if branch is not None:
            order_filter &= Q(branch=branch)
        voids = Order.objects.filter(order_filter, status=Order.Status.VOIDED)
        discounts = Order.objects.filter(order_filter, discount_amount__gt=0)

        payments = MpesaTransaction.objects.filter(
            created_at__gte=start_at, created_at__lt=end_at,
        )
        reconciliations = ShiftReconciliation.objects.filter(
            closed_at__gte=start_at, closed_at__lt=end_at,
        )
        manual_audits = AuditLog.objects.filter(
            timestamp__gte=start_at, timestamp__lt=end_at,
            action_type=AuditLog.ActionTypes.MANUAL_PAYMENT_CONFIRMATION,
        )
        movements = StockAuditLog.objects.filter(
            timestamp__gte=start_at, timestamp__lt=end_at,
        )
        transfers = TransferRequest.objects.filter(
            requested_at__gte=start_at, requested_at__lt=end_at,
        )
        if branch is not None:
            payments = payments.filter(order__branch=branch)
            reconciliations = reconciliations.filter(branch=branch)
            manual_audits = manual_audits.filter(user__branch=branch)
            movements = movements.filter(branch=branch)
            transfers = transfers.filter(Q(from_branch=branch) | Q(to_branch=branch))

        variance = reconciliations.aggregate(
            net=Coalesce(
                Sum('cash_variance'), Decimal('0.00'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            flagged=Count('id', filter=Q(requires_manager_review=True)),
            unverified=Count('id', filter=Q(requires_manager_review=True, is_verified_by_manager=False)),
        )
        return {
            'voids': voids.count(),
            'discounted_orders': discounts.count(),
            'discount_total': money(discounts.aggregate(total=Sum('discount_amount'))['total']),
            'manual_payment_confirmations': manual_audits.count(),
            'failed_or_reconciliation_payments': payments.filter(status__in=cls.FAILED_PAYMENT_STATUSES).count(),
            'shift_net_variance': money(variance['net']),
            'flagged_shift_variances': variance['flagged'],
            'unverified_shift_variances': variance['unverified'],
            'stock_movements': list(movements.values('reason').annotate(events=Count('id')).order_by('reason')),
            'transfers': list(transfers.values('status').annotate(events=Count('id')).order_by('status')),
        }

    @classmethod
    def _fulfilment_summary(cls, start_at, end_at, branch):
        assignments = DeliveryAssignment.objects.filter(
            assigned_at__gte=start_at, assigned_at__lt=end_at,
        )
        if branch is not None:
            assignments = assignments.filter(order__branch=branch)
        durations = assignments.filter(
            dispatched_at__isnull=False, completed_at__isnull=False,
        ).annotate(duration=F('completed_at') - F('dispatched_at')).aggregate(avg=Avg('duration'))
        average = durations['avg']
        riders = list(assignments.values(
            'rider_id', 'rider__user__first_name', 'rider__user__last_name',
            'rider__user__username',
        ).annotate(
            assignments=Count('id'),
            delivered=Count('id', filter=Q(status=DeliveryAssignment.DeliveryStatus.DELIVERED)),
            disputed=Count('id', filter=Q(customer_disputed=True)),
        ).order_by('-delivered'))
        return {
            'assignments': assignments.count(),
            'delivered': assignments.filter(status=DeliveryAssignment.DeliveryStatus.DELIVERED).count(),
            'disputes': assignments.filter(customer_disputed=True).count(),
            'average_delivery_minutes': round(average.total_seconds() / 60, 2) if average else 0,
            'riders': riders,
        }

    @classmethod
    def _promotion_return_summary(cls, start_at, end_at, branch):
        redemptions = CouponRedemption.objects.filter(
            created_at__gte=start_at, created_at__lt=end_at,
        )
        returns = ReturnRequest.objects.filter(
            created_at__gte=start_at, created_at__lt=end_at,
        )
        if branch is not None:
            redemptions = redemptions.filter(order__branch=branch)
            returns = returns.filter(order__branch=branch)
        promotion = redemptions.aggregate(
            count=Count('id'), discount=Sum('discount_amount'),
        )
        return {
            'promotion_redemptions': promotion['count'],
            'promotion_discount': money(promotion['discount']),
            'returns': list(returns.values('status').annotate(
                requests=Count('id'), units=Sum('quantity'),
            ).order_by('status')),
            'pending_manual_refunds': returns.filter(
                refund_status=ReturnRequest.RefundStatus.PENDING_MANUAL,
            ).count(),
        }
