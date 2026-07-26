# apps/reports/shift_services.py
#
# CRITICAL FIX: get_branch_daily_summary() was filtering status=COMPLETED
# only. Online orders never reach COMPLETED -- they terminate at
# DELIVERED (RiderUpdateDeliveryStatusView) or COLLECTED
# (ConfirmPickupView). This meant every online sale was silently
# excluded from branch revenue reports. Now uses status__in=[...].
#
# Also fixed: staff_breakdown grouped by processed_by with no order_type
# filter -- since online orders also have processed_by=customer, this
# would put customers in the staff performance table once the status
# fix landed. Now scoped to order_type=WALK_IN specifically.
#
# Added: COD to the payment-method breakdown (didn't exist when this
# file was first written), and a walk-in vs online channel split.
#
# get_shift_summary is UNCHANGED -- staff-scoped queries only ever
# match walk-in orders in practice (processed_by=customer for online
# orders never matches a staff_user), so the COMPLETED-only filter
# there was never actually wrong.
#
# DEPLOYMENT NOTE: cache keys are unchanged, but the cached VALUE shape
# now includes new fields (cod, channel_breakdown). Any cache entry
# written before this fix and still within its 5-minute TTL will return
# stale, old-shape data. Flush the reports cache after deploying, or
# simply wait out the TTL.

from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, datetime, time
# now:
from django.db.models import Sum, Count, Avg, Max, Min, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.core.cache import cache


def _quantize_money(val):
    """
    Quantize to exactly 2 decimal places explicitly -- SQLite's SUM() on a
    DecimalField doesn't reliably preserve decimal_places padding the way
    PostgreSQL's NUMERIC does (e.g. returns Decimal('500') instead of
    Decimal('500.00')). Keeps output identical regardless of DB backend.
    """
    return Decimal(str(val or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ShiftReportService:
    """
    Performance contract:
    - All status counts: one aggregate query (not three .count() calls)
    - All financial aggregates: one aggregate query
    - total_items_sold: one OrderItem query with direct field traversal
    - Branch staff breakdown: one grouped queryset, not a per-staff loop
    - Date filtering: datetime range so PostgreSQL can use the created_at index
    - Results cached in Redis per staff/branch/period - 5 minute TTL
    """

    CACHE_TTL = 60 * 5

    # "Successfully sold" statuses across BOTH order flows:
    #   COMPLETED  -- walk-in sales (POSSalesService)
    #   DELIVERED  -- online delivery orders (logistics rider flow)
    #   COLLECTED  -- online pickup orders (ConfirmPickupView)
    SUCCESSFUL_SALE_STATUSES = [
        'COMPLETED', 'DELIVERED', 'CUSTOMER_CONFIRMED', 'COLLECTED',
    ]

    # ------------------------------------------------------------------
    # DATE RANGE RESOLVER
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_date_range(period='today', custom_start=None, custom_end=None):
        """
        Returns (start_datetime, end_datetime) as timezone-aware datetimes.
        Supported periods: today, yesterday, last_week, last_month, 7_days,
        30_days, custom.
        7_days/30_days are ROLLING windows anchored to now() (dashboard
        KPI/timeline view) — distinct from last_week/last_month, which
        are calendar-anchored (shift/branch reports).
        """
        if period in ('7_days', '30_days'):
            days = 7 if period == '7_days' else 30
            end_dt = timezone.now()
            start_dt = end_dt - timedelta(days=days)
            return start_dt, end_dt

        today = timezone.localdate()

        if period == 'today':
            start_date = end_date = today
        elif period == 'yesterday':
            start_date = end_date = today - timedelta(days=1)
        elif period == 'last_week':
            start_date = today - timedelta(days=today.weekday() + 7)
            end_date = start_date + timedelta(days=6)
        elif period == 'last_month':
            first_this = today.replace(day=1)
            end_date = first_this - timedelta(days=1)
            start_date = end_date.replace(day=1)
        elif period == 'custom':
            if not custom_start or not custom_end:
                raise ValueError(
                    "custom_start and custom_end are required for 'custom' period."
                )
            start_date, end_date = custom_start, custom_end
        else:
            start_date = end_date = today

        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(datetime.combine(start_date, time.min), tz)
        end_dt = timezone.make_aware(datetime.combine(end_date, time.max), tz)
        return start_dt, end_dt

    # ------------------------------------------------------------------
    # STAFF SHIFT SUMMARY (unchanged -- see note above on why)
    # ------------------------------------------------------------------

    @staticmethod
    def get_shift_summary(staff_user, period='today', custom_start=None, custom_end=None):
        """
        Complete shift summary for one staff member.
        Staff-scoped (processed_by=staff_user) -- in practice this only
        ever matches WALK_IN orders, since online orders always have
        processed_by=customer. The COMPLETED-only filter here is
        therefore correct as-is; no change needed.
        """
        from orders.models import Order, OrderItem

        cache_key = f"shift:{staff_user.id}:{period}:{custom_start}:{custom_end}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        start_dt, end_dt = ShiftReportService.resolve_date_range(
            period, custom_start, custom_end
        )

        base_filter = dict(
            processed_by=staff_user,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
            branch=staff_user.branch,
        )

        counts = Order.objects.filter(**base_filter).aggregate(
            completed=Count('id', filter=Q(status=Order.Status.COMPLETED)),
            voided=Count('id', filter=Q(status=Order.Status.VOIDED)),
            cancelled=Count('id', filter=Q(status=Order.Status.CANCELLED)),
        )
        completed_count = counts['completed']

        fin = Order.objects.filter(
            **base_filter,
            status=Order.Status.COMPLETED,
        ).aggregate(
            total_revenue=Sum('total_payable'),
            cash_total=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.CASH)),
            paybill_total=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.PAYBILL)),
            mpesa_total=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.MPESA_STK)),
            total_discounts=Sum('discount_amount'),
            avg_sale=Avg('total_payable'),
            highest_sale=Max('total_payable'),
            lowest_sale=Min('total_payable'),
        )

        d = _quantize_money

        total_rev = d(fin['total_revenue'])
        cash = d(fin['cash_total'])
        paybill = d(fin['paybill_total'])
        mpesa = d(fin['mpesa_total'])

        items_total = OrderItem.objects.filter(
            order__processed_by=staff_user,
            order__status=Order.Status.COMPLETED,
            order__branch=staff_user.branch,
            order__created_at__gte=start_dt,
            order__created_at__lte=end_dt,
        ).aggregate(total=Sum('quantity'))['total'] or 0

        orders_detail = list(
            Order.objects.filter(**base_filter).order_by('created_at').values(
                'order_number', 'created_at', 'total_payable',
                'payment_method', 'status', 'discount_amount',
            )
        )

        cash_pct = round(float(cash / total_rev * 100), 1) if total_rev else 0
        paybill_pct = round(float(paybill / total_rev * 100), 1) if total_rev else 0
        mpesa_pct = round(float(mpesa / total_rev * 100), 1) if total_rev else 0

        average_discount = (
            (d(fin['total_discounts']) / completed_count).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if completed_count else Decimal('0.00')
        )

        result = {
            'staff': {
                'id': str(staff_user.id),
                'name': staff_user.get_full_name() or staff_user.username,
                'branch': staff_user.branch.name if staff_user.branch else None,
            },
            'period': {
                'label': period,
                'start': start_dt.date().isoformat(),
                'end': end_dt.date().isoformat(),
            },
            'summary': {
                'completed_sales': completed_count,
                'voided_sales': counts['voided'],
                'cancelled_sales': counts['cancelled'],
                'total_items_sold': items_total,
            },
            'revenue': {
                'total': str(total_rev),
                'cash': str(cash),
                'paybill': str(paybill),
                'mpesa_stk': str(mpesa),
                'cash_percent': cash_pct,
                'paybill_percent': paybill_pct,
                'mpesa_percent': mpesa_pct,
            },
            'kpis': {
                'average_sale_value': str(d(fin['avg_sale'])),
                'highest_sale': str(d(fin['highest_sale'])),
                'lowest_sale': str(d(fin['lowest_sale'])),
                'total_discounts_given': str(d(fin['total_discounts'])),
                'average_discount': str(average_discount),
            },
            'orders': [
                {
                    'order_number': o['order_number'],
                    'time': o['created_at'].strftime('%H:%M') if o['created_at'] else '',
                    'total': str(o['total_payable']),
                    'discount': str(o['discount_amount']),
                    'payment': o['payment_method'],
                    'status': o['status'],
                }
                for o in orders_detail
            ],
        }

        cache.set(cache_key, result, ShiftReportService.CACHE_TTL)
        return result

    # ------------------------------------------------------------------
    # BRANCH DAILY SUMMARY -- the actual fix
    # ------------------------------------------------------------------

    @staticmethod
    def get_branch_daily_summary(branch, period='today', custom_start=None, custom_end=None):
        """
        Cross-channel branch summary. Now correctly includes:
          - Walk-in sales (COMPLETED)
          - Online deliveries (DELIVERED)
          - Online pickups (COLLECTED)
        Previously only counted COMPLETED, silently excluding all
        online revenue.

        staff_breakdown is scoped to order_type=WALK_IN specifically --
        online orders have processed_by=customer, which would otherwise
        put customers in a "staff performance" table.

        channel_breakdown is new: walk-in vs online revenue split,
        since that's now a meaningful question with two live channels.
        """
        from orders.models import Order, OrderItem

        cache_key = f"branch:{branch.id}:{period}:{custom_start}:{custom_end}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        start_dt, end_dt = ShiftReportService.resolve_date_range(
            period, custom_start, custom_end
        )

        # FIX: status__in, not status= -- includes DELIVERED and COLLECTED
        successful_filter = dict(
            branch=branch,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
            status__in=ShiftReportService.SUCCESSFUL_SALE_STATUSES,
        )

        fin = Order.objects.filter(**successful_filter).aggregate(
            total_revenue=Sum('total_payable'),
            cash_total=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.CASH)),
            paybill_total=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.PAYBILL)),
            mpesa_total=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.MPESA_STK)),
            # NEW: COD didn't exist when this file was first written
            cod_total=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.COD)),
            total_discounts=Sum('discount_amount'),
            avg_sale=Avg('total_payable'),
            order_count=Count('id'),
        )

        d = _quantize_money
          

        # FIX: status__in matches the corrected successful_filter above
        total_items = OrderItem.objects.filter(
            order__branch=branch,
            order__status__in=ShiftReportService.SUCCESSFUL_SALE_STATUSES,
            order__created_at__gte=start_dt,
            order__created_at__lte=end_dt,
        ).aggregate(total=Sum('quantity'))['total'] or 0

        # NEW: walk-in vs online channel split
        channel_totals = Order.objects.filter(**successful_filter).aggregate(
            walk_in_revenue=Sum(
                'total_payable', filter=Q(order_type=Order.OrderType.WALK_IN)
            ),
            online_revenue=Sum(
                'total_payable',
                filter=Q(order_type__in=[
                    Order.OrderType.ONLINE_DELIVERY,
                    Order.OrderType.ONLINE_PICKUP,
                ]),
            ),
            walk_in_count=Count('id', filter=Q(order_type=Order.OrderType.WALK_IN)),
            online_count=Count(
                'id',
                filter=Q(order_type__in=[
                    Order.OrderType.ONLINE_DELIVERY,
                    Order.OrderType.ONLINE_PICKUP,
                ]),
            ),
        )

        # FIX: staff_breakdown scoped to WALK_IN only -- online orders'
        # processed_by=customer would otherwise pollute this table
        staff_breakdown = list(
            Order.objects.filter(
                **successful_filter,
                order_type=Order.OrderType.WALK_IN,
            ).values(
                'processed_by__id',
                'processed_by__first_name',
                'processed_by__last_name',
                'processed_by__username',
            ).annotate(
                sales_count=Count('id'),
                revenue=Sum('total_payable'),
                cash=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.CASH)),
                paybill=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.PAYBILL)),
                mpesa=Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.MPESA_STK)),
                discounts=Sum('discount_amount'),
            ).order_by('-revenue')
        )

        result = {
            'branch': branch.name,
            'period': {
                'label': period,
                'start': start_dt.date().isoformat(),
                'end': end_dt.date().isoformat(),
            },
            'branch_totals': {
                'total_revenue': str(d(fin['total_revenue'])),
                'cash': str(d(fin['cash_total'])),
                'paybill': str(d(fin['paybill_total'])),
                'mpesa_stk': str(d(fin['mpesa_total'])),
                'cod': str(d(fin['cod_total'])),
                'total_discounts': str(d(fin['total_discounts'])),
                'average_sale': str(d(fin['avg_sale'])),
                'total_orders': fin['order_count'] or 0,
                'total_items_sold': total_items,
            },
            'channel_breakdown': {
                'walk_in': {
                    'revenue': str(d(channel_totals['walk_in_revenue'])),
                    'order_count': channel_totals['walk_in_count'] or 0,
                },
                'online': {
                    'revenue': str(d(channel_totals['online_revenue'])),
                    'order_count': channel_totals['online_count'] or 0,
                },
            },
            'staff_breakdown': [
                {
                    'staff_id': str(s['processed_by__id']),
                    'name': (
                        f"{s['processed_by__first_name']} "
                        f"{s['processed_by__last_name']}".strip()
                        or s['processed_by__username']
                    ),
                    'sales_count': s['sales_count'],
                    'revenue': str(d(s['revenue'])),
                    'cash': str(d(s['cash'])),
                    'paybill': str(d(s['paybill'])),
                    'mpesa_stk': str(d(s['mpesa'])),
                    'discounts': str(d(s['discounts'])),
                }
                for s in staff_breakdown
            ],
        }

        cache.set(cache_key, result, ShiftReportService.CACHE_TTL)
        return result
    
    # ------------------------------------------------------------------
    # DASHBOARD KPI + TIMELINE (manager/admin analytics dashboard)
    # ------------------------------------------------------------------

    @staticmethod
    def get_dashboard_metrics(branch=None, period='7_days'):
        """
        Cross-channel KPI totals + daily revenue/volume timeline for the
        AnalyticsDashboardMetricsPartialView. branch=None = system-wide
        (super admin 'ALL' scope). Reuses SUCCESSFUL_SALE_STATUSES so
        online orders (DELIVERED/COLLECTED) are never silently excluded,
        same fix already applied to get_branch_daily_summary.
        """
        from orders.models import Order

        cache_key = f"dashboard:{branch.id if branch else 'ALL'}:{period}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        start_dt, end_dt = ShiftReportService.resolve_date_range(period)

        base_orders = Order.objects.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt,
            status__in=ShiftReportService.SUCCESSFUL_SALE_STATUSES,
        )
        if branch is not None:
            base_orders = base_orders.filter(branch=branch)

        metrics = base_orders.aggregate(
            gross_revenue=Coalesce(Sum('total_payable'), Decimal('0.00')),
            total_sales_volume=Count('id'),
            cash_sales_sum=Coalesce(
                Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.CASH)),
                Decimal('0.00'),
            ),
            mpesa_sales_sum=Coalesce(
                Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.MPESA_STK)),
                Decimal('0.00'),
            ),
            cod_sales_sum=Coalesce(
                Sum('total_payable', filter=Q(payment_method=Order.PaymentMethod.COD)),
                Decimal('0.00'),
            ),
        )

        timeline = (
            base_orders.annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(daily_revenue=Sum('total_payable'), daily_count=Count('id'))
            .order_by('day')
        )

        result = {
            'gross_revenue': metrics['gross_revenue'],
            'total_sales_volume': metrics['total_sales_volume'],
            'cash_sales': metrics['cash_sales_sum'],
            'mpesa_sales': metrics['mpesa_sales_sum'],
            'cod_sales': metrics['cod_sales_sum'],
            'chart_labels': [e['day'].strftime('%b %d') for e in timeline],
            'chart_revenue_dataset': [float(e['daily_revenue']) for e in timeline],
            'chart_volume_dataset': [e['daily_count'] for e in timeline],
            'timeframe': period,
        }
        cache.set(cache_key, result, ShiftReportService.CACHE_TTL)
        return result
