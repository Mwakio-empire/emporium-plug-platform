from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import timedelta
from analytics.models import AuditLog
from branches.models import Branch
from orders.models import Order


class AuditTrackingService:
    """
    Encapsulated tracking engine logging mission-critical operations 
    to maintain a clear and continuous chain of accountability.
    """
    @classmethod
    def log_action(cls, user, action_type, description, ip_address=None):
        """
        Generates an unmodifiable audit entry capturing standard system state events.
        """
        return AuditLog.objects.create(
            user=user,
            action_type=action_type,
            description=description,
            ip_address=ip_address
        )


class BusinessIntelligenceService:
    """
    High-performance analytical computing array providing aggregated metrics 
    across all global storefront distribution hubs.
    """
    @classmethod
    def get_consolidated_dashboard_metrics(cls):
        """
        Computes system-wide financial performance indicators and tracking trends,
        safely filtering out unfulfilled or pending transactions.
        """
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)

        # Global system revenue calculation (Past 30 Days)
        successful_statuses = [
            Order.Status.COMPLETED,
            Order.Status.DELIVERED,
            Order.Status.CUSTOMER_CONFIRMED,
            Order.Status.COLLECTED,
        ]
        revenue_metrics = Order.objects.filter(
            status__in=successful_statuses,
            created_at__date__gte=thirty_days_ago
        ).aggregate(
            total_revenue=Sum('total_payable'),
            total_orders=Count('id')
        )

        # Performance Breakdown segmented at individual physical branch nodes
        branch_performance = Branch.objects.annotate(
            branch_revenue=Sum('orders__total_payable', filter=Q(orders__status__in=successful_statuses)),
            branch_order_count=Count('orders__id', filter=Q(orders__status__in=successful_statuses))
        ).values('id', 'name', 'branch_revenue', 'branch_order_count')

        return {
            "total_revenue": revenue_metrics["total_revenue"] or 0.00,
            "total_orders": revenue_metrics["total_orders"] or 0,
            "branch_performance": list(branch_performance),
        }
