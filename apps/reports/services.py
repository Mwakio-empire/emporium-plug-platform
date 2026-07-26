import datetime

from django.db import models
from django.db.models import Sum, Count, Avg, F, Q, ExpressionWrapper, DurationField
from datetime import timedelta
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from branches.models import Branch
from catalog.models import Product
from orders.models import Order
from .models import ShiftReconciliation, OperationalAuditRiskLog

User = get_user_model()

class AnalyticsEngineService:
    """
    State-of-the-art multi-domain database intelligence orchestrator compiling
    high-performance data matrices for executive planning models.
    """

    @classmethod
    def compile_transaction_trends_matrix(cls, start_date, end_date):
        """
        Submodule 11.1: Aggregates metrics grouping trends by physical branch nodes, 
        cashier identity records, payment vectors, and incoming sales channels.
        """
        base_queryset = Order.objects.filter(
            created_at__range=(start_date, end_date),
            status='COMPLETED'
        )

        # 1. Performance across physical branch network nodes
        branch_trends = Branch.objects.annotate(
            revenue=Coalesce(
                Sum('orders__total_payable', filter=Q(orders__status='COMPLETED', orders__created_at__range=(start_date, end_date))),
                Decimal('0.00'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            ),
            volume=Count('orders__id', filter=Q(orders__status='COMPLETED', orders__created_at__range=(start_date, end_date)))
        ).values('id', 'name', 'revenue', 'volume')
        # 2. Performance grouped by sales channels
        channel_trends = base_queryset.values('order_type').annotate(
            revenue=Sum('total_payable'),
            volume=Count('id')
        )

        # 3. Financial breakdown segmented by payment vectors
        # Supports CASH vs MPESA split across payment records

        payment_vector_trends = base_queryset.values('payment_method').annotate(
            revenue=Sum('total_payable'),
            volume=Count('id')
        )   

        # 4. Performance metrics tracked by individual cashier processing records
        staff_trends = User.objects.filter(
            processed_orders__created_at__range=(start_date, end_date),
            processed_orders__status='COMPLETED'
        ).annotate(
            revenue=Sum('processed_orders__total_payable'),
            volume=Count('processed_orders__id')
        ).values('id', 'email', 'revenue', 'volume')
        return {
            "generated_at": timezone.now(),
            "time_window": {"start": start_date, "end": end_date},
            "branch_performance_matrix": list(branch_trends),
            "channel_performance_matrix": list(channel_trends),
            "payment_vector_matrix": list(payment_vector_trends),
            "staff_efficiency_matrix": list(staff_trends)
        }

    @classmethod
    def compile_inventory_and_logistics_intelligence(cls):
        """
        Submodule 11.1: Tracks dead stock indicators, top-velocity items, slow catalog lines, 
        and fulfillment durations across active delivery pathways.
        """
        thirty_days_ago = timezone.now() - datetime.timedelta(days=30)

        # 1. Top Selling Velocity Products

        top_products = Product.objects.annotate(
            units_sold=Coalesce(Sum('order_items__quantity', filter=Q(order_items__order__status='COMPLETED')), 0),
            gross_revenue=Coalesce(
                Sum(ExpressionWrapper(F('order_items__quantity') * F('order_items__unit_price'), output_field=models.DecimalField(max_digits=12, decimal_places=2)), filter=Q(order_items__order__status='COMPLETED')),
                Decimal('0.00'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        ).order_by('-units_sold')[:10].values('id', 'name', 'sku', 'units_sold', 'gross_revenue')
        # 2. Slow-Moving & Dead Stock Tracking Analytics
        # Defined as items holding current inventory stock footprints but showing zero sales over a 30 day window

        dead_stock = Product.objects.annotate(
            recent_sales=Coalesce(Sum('order_items__quantity', filter=Q(order_items__order__status='COMPLETED', order_items__order__created_at__gte=thirty_days_ago)), 0)
        ).filter(
            recent_sales=0,
            stocks__quantity__gt=0  # Has inventory but no sales traction
        ).distinct().values('id', 'name', 'sku')[:10]

        # 3. Turnaround Delivery Timeline Metrics
        # Computes delivery duration performance across the logistics framework
# WITH:
        delivery_metrics = Order.objects.filter(
            status='COMPLETED',
            delivery_assignment__isnull=False,
            delivery_assignment__completed_at__isnull=False
        ).annotate(
            duration=ExpressionWrapper(
                F('delivery_assignment__completed_at') - F('delivery_assignment__dispatched_at'),
                output_field=DurationField()
            )
        ).aggregate(
            average_delivery_seconds=Avg('duration')
        )

        avg_seconds = delivery_metrics['average_delivery_seconds']
        avg_minutes = (avg_seconds.total_seconds() / 60) if avg_seconds else 0.0

        return {
            "top_performing_products": list(top_products),
            "dead_stock_lines": list(dead_stock),
            "average_fulfillment_minutes": round(avg_minutes, 2)
        }


class ComplianceAuditService:
    """
    Submodule 11.2: Orchestrates comprehensive risk audit captures and highlights 
    system compliance concerns for manager review trails.
    """

    @classmethod
    def generate_risk_alert_summary(cls, lookback_days=1):
        """Compiles compliance concerns across staff activities."""
        time_threshold = timezone.now() - datetime.timedelta(days=lookback_days)
        
        void_count = OperationalAuditRiskLog.objects.filter(action_type='ORDER_VOID', timestamp__gte=time_threshold).count()
        manual_pay_count = OperationalAuditRiskLog.objects.filter(action_type='MANUAL_MPESA_MATCH', timestamp__gte=time_threshold).count()
        
        cash_variances = ShiftReconciliation.objects.filter(closed_at__gte=time_threshold).aggregate(
            cumulative_variance=Sum('cash_variance'),
            absolute_variance_incidents=Count('id', filter=~Q(cash_variance=0.00))
        )

        critical_incidents = OperationalAuditRiskLog.objects.filter(
            severity__in=[OperationalAuditRiskLog.RiskSeverity.HIGH, OperationalAuditRiskLog.RiskSeverity.CRITICAL],
            timestamp__gte=time_threshold
        ).values('timestamp', 'action_type', 'initiator__email', 'justification_trail')

        return {
            "voided_transactions_count": void_count,
            "manual_payment_confirmations_count": manual_pay_count,
            "net_cash_variance": cash_variances['cumulative_variance'] or 0.00,
            "variance_incidents_logged": cash_variances['absolute_variance_incidents'] or 0,
            "flagged_critical_incidents": list(critical_incidents)
        }