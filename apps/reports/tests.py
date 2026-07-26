# apps/reports/tests.py
#
# Django's built-in test runner (TestCase + APITestCase).
# Single file, following Root_Directory.md's own convention for apps
# without a dedicated tests/ folder (reports/ wasn't listed with one,
# unlike catalog/orders/logistics/core).
#
# Test cache is in-memory during test runs (settings.py already swaps
# CACHES to LocMemCache when 'test' is in sys.argv) -- no Redis
# dependency needed here, and it lets us verify caching behavior
# reliably without flakiness.

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.core.cache import cache
from django.contrib.auth import get_user_model

from branches.models import Branch
from catalog.models import Category, Product
from orders.models import Order, OrderItem
from reports.shift_services import ShiftReportService

User = get_user_model()


class ReportsTestDataMixin:

    def setUp(self):
        cache.clear()  # ensure no cross-test cache pollution

        self.branch = Branch.objects.create(
            name="Reports Test Branch", location="Test",
        )
        self.other_branch = Branch.objects.create(
            name="Reports Other Branch", location="Elsewhere",
        )

        self.cashier = User.objects.create_user(
            username='reportscashier0001', phone_number='+254711100001',
            email='reportscashier0001@test.com', first_name='Counter',
            last_name='Cashier', password='CashierPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        self.manager = User.objects.create_user(
            username='reportsmanager0001', phone_number='+254711100002',
            email='reportsmanager0001@test.com', first_name='Branch',
            last_name='Manager', password='ManagerPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.customer = User.objects.create_user(
            username='reportscust0001', phone_number='+254711100003',
            email='reportscust0001@test.com', first_name='Online',
            last_name='Customer', password='CustPass123!',
            role=User.Role.CUSTOMER,
        )

        self.category = Category.objects.create(
            name="Reports Category", slug="reports-category",
        )
        self.product = Product.objects.create(
            name="Reports Product", slug="reports-product",
            category=self.category, price=Decimal("1000.00"),
            status=Product.Status.ACTIVE,
        )

    def _create_order(self, *, order_type, status, payment_method,
                       processed_by, total, branch=None):
        return Order.objects.create(
            branch=branch or self.branch,
            customer=self.customer if order_type != Order.OrderType.WALK_IN else None,
            order_type=order_type,
            customer_phone='+254700111111',
            payment_method=payment_method,
            status=status,
            processed_by=processed_by,
            subtotal=total,
            total_payable=total,
        )


class BranchDailySummaryRevenueTests(ReportsTestDataMixin, TestCase):
    """
    The critical regression suite for the bug found this session:
    online orders were silently excluded from branch revenue because
    the report only counted status=COMPLETED, and online orders never
    reach COMPLETED (they terminate at DELIVERED or COLLECTED).
    """

    def test_delivered_online_order_counted_in_branch_revenue(self):
        """
        WHAT: An ONLINE_DELIVERY order with status=DELIVERED
        EXPECT: Its total_payable IS included in branch_totals.total_revenue
                -- this is THE bug. Before the fix, this assertion would
                have failed because DELIVERED was never in the status filter.
        """
        self._create_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.DELIVERED,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.customer,
            total=Decimal('2000.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(summary['branch_totals']['total_revenue'], '2000.00')

    def test_collected_pickup_order_counted_in_branch_revenue(self):
        """
        WHAT: An ONLINE_PICKUP order with status=COLLECTED
        EXPECT: Included in branch_totals -- same bug, different terminal status
        """
        self._create_order(
            order_type=Order.OrderType.ONLINE_PICKUP,
            status=Order.Status.COLLECTED,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.customer,
            total=Decimal('1500.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(summary['branch_totals']['total_revenue'], '1500.00')

    def test_pending_order_not_counted(self):
        """
        WHAT: An order still PENDING (awaiting M-Pesa confirmation)
        EXPECT: NOT counted -- it hasn't successfully sold yet
        """
        self._create_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.PENDING,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.customer,
            total=Decimal('999.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(summary['branch_totals']['total_revenue'], '0.00')

    def test_cancelled_order_not_counted(self):
        """WHAT: A CANCELLED order (e.g. auto-cancelled abandoned checkout)
        EXPECT: NOT counted"""
        self._create_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.CANCELLED,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.customer,
            total=Decimal('999.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(summary['branch_totals']['total_revenue'], '0.00')

    def test_walk_in_completed_still_counted(self):
        """
        WHAT: A normal WALK_IN order with status=COMPLETED (the original,
              always-worked case)
        EXPECT: Still counted -- confirms the fix didn't break the
                existing walk-in behavior while fixing the online gap
        """
        self._create_order(
            order_type=Order.OrderType.WALK_IN,
            status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier,
            total=Decimal('500.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(summary['branch_totals']['total_revenue'], '500.00')

    def test_cod_payment_method_totaled_correctly(self):
        """
        WHAT: A DELIVERED order paid via COD
        EXPECT: branch_totals['cod'] reflects it -- COD didn't exist
                when this file was first written, confirming it was
                properly added
        """
        self._create_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.DELIVERED,
            payment_method=Order.PaymentMethod.COD,
            processed_by=self.customer,
            total=Decimal('800.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(summary['branch_totals']['cod'], '800.00')

    def test_other_branch_orders_excluded(self):
        """WHAT: A completed order at a DIFFERENT branch
        EXPECT: Not counted in this branch's summary"""
        self._create_order(
            order_type=Order.OrderType.WALK_IN,
            status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier,
            total=Decimal('300.00'),
            branch=self.other_branch,
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(summary['branch_totals']['total_revenue'], '0.00')


class StaffBreakdownExclusionTests(ReportsTestDataMixin, TestCase):
    """
    The second bug found this session: staff_breakdown grouped by
    processed_by with no order_type filter -- since online orders also
    have processed_by=customer, customers would appear in a "staff
    performance" table once the revenue fix landed.
    """

    def test_customer_never_appears_in_staff_breakdown(self):
        """
        WHAT: An online order processed_by=customer, PLUS a walk-in
              order processed_by=cashier
        EXPECT: staff_breakdown contains ONLY the cashier -- the
                customer's name never appears, even though their order
                now correctly counts toward total_revenue
        """
        self._create_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.DELIVERED,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.customer,
            total=Decimal('1000.00'),
        )
        self._create_order(
            order_type=Order.OrderType.WALK_IN,
            status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier,
            total=Decimal('500.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')

        staff_ids = [s['staff_id'] for s in summary['staff_breakdown']]
        self.assertIn(str(self.cashier.id), staff_ids)
        self.assertNotIn(str(self.customer.id), staff_ids)
        self.assertEqual(len(summary['staff_breakdown']), 1)


class ChannelBreakdownTests(ReportsTestDataMixin, TestCase):

    def test_walk_in_and_online_split_correctly(self):
        """
        WHAT: One walk-in sale (500) and one online delivery (1500)
        EXPECT: channel_breakdown correctly attributes each to its
                own channel, both included in total_revenue (2000)
        """
        self._create_order(
            order_type=Order.OrderType.WALK_IN,
            status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier,
            total=Decimal('500.00'),
        )
        self._create_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.DELIVERED,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.customer,
            total=Decimal('1500.00'),
        )

        summary = ShiftReportService.get_branch_daily_summary(self.branch, period='today')

        self.assertEqual(summary['channel_breakdown']['walk_in']['revenue'], '500.00')
        self.assertEqual(summary['channel_breakdown']['online']['revenue'], '1500.00')
        self.assertEqual(summary['branch_totals']['total_revenue'], '2000.00')


class CachingTests(ReportsTestDataMixin, TestCase):

    def test_second_call_returns_cached_result(self):
        """
        WHAT: Call get_branch_daily_summary, create a NEW order, call
              again within the same test (well within the 5-min TTL)
        EXPECT: Second call returns the SAME (stale) total -- proving
                the cache is actually being read, not recomputed
        """
        self._create_order(
            order_type=Order.OrderType.WALK_IN,
            status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier,
            total=Decimal('500.00'),
        )
        first = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(first['branch_totals']['total_revenue'], '500.00')

        # New order created AFTER the first call -- should NOT appear
        # in the second call if caching is actually working
        self._create_order(
            order_type=Order.OrderType.WALK_IN,
            status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH,
            processed_by=self.cashier,
            total=Decimal('999.00'),
        )
        second = ShiftReportService.get_branch_daily_summary(self.branch, period='today')
        self.assertEqual(second['branch_totals']['total_revenue'], '500.00')  # still stale


class DateRangeResolverTests(TestCase):

    def test_custom_period_without_dates_raises_value_error(self):
        """WHAT: period='custom' with no custom_start/custom_end
        EXPECT: ValueError, clear message"""
        with self.assertRaises(ValueError):
            ShiftReportService.resolve_date_range(period='custom')

    def test_yesterday_is_one_day_before_today(self):
        """WHAT: resolve_date_range('yesterday')
        EXPECT: start and end date both equal today - 1 day"""
        start_dt, end_dt = ShiftReportService.resolve_date_range(period='yesterday')
        expected = date.today() - timedelta(days=1)
        self.assertEqual(start_dt.date(), expected)
        self.assertEqual(end_dt.date(), expected)

    def test_custom_period_with_dates_returns_exact_range(self):
        """WHAT: Explicit custom_start/custom_end
        EXPECT: Returned range matches exactly"""
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)
        start_dt, end_dt = ShiftReportService.resolve_date_range(
            period='custom', custom_start=start, custom_end=end,
        )
        self.assertEqual(start_dt.date(), start)
        self.assertEqual(end_dt.date(), end)


class ReportsViewPermissionTests(ReportsTestDataMixin, APITestCase):

    def test_my_shift_report_requires_authentication(self):
        """WHAT: GET /api/reports/my-shift/ with no auth
        EXPECT: 401"""
        response = self.client.get(reverse('reports:my-shift'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_any_authenticated_staff_can_view_own_shift(self):
        """WHAT: Cashier views their own shift report
        EXPECT: 200"""
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get(reverse('reports:my-shift'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_customer_cannot_view_branch_daily_summary(self):
        """WHAT: A CUSTOMER attempts branch-daily
        EXPECT: 403 -- IsBranchManagerOrAbove excludes customers"""
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(reverse('reports:branch-daily'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cashier_cannot_view_branch_daily_summary(self):
        """WHAT: Plain STAFF (not manager) attempts branch-daily
        EXPECT: 403"""
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get(reverse('reports:branch-daily'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_view_branch_daily_summary(self):
        """WHAT: BRANCH_MANAGER requests branch-daily
        EXPECT: 200, includes the fixed channel_breakdown key"""
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(reverse('reports:branch-daily'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('channel_breakdown', response.data)

    def test_invalid_custom_date_format_rejected(self):
        """WHAT: ?period=custom&start=not-a-date
        EXPECT: 400"""
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(
            reverse('reports:branch-daily') + '?period=custom&start=not-a-date&end=2026-01-31'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_custom_period_missing_dates_rejected(self):
        """WHAT: ?period=custom with no start/end at all
        EXPECT: 400"""
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(reverse('reports:branch-daily') + '?period=custom')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class DashboardMetricsServiceTests(ReportsTestDataMixin, TestCase):

    def test_delivered_online_order_included_in_dashboard_metrics(self):
        """Same class of bug as get_branch_daily_summary -- DELIVERED/COLLECTED must count."""
        self._create_order(
            order_type=Order.OrderType.ONLINE_DELIVERY,
            status=Order.Status.DELIVERED,
            payment_method=Order.PaymentMethod.MPESA_STK,
            processed_by=self.customer,
            total=Decimal('2000.00'),
        )
        from reports.shift_services import ShiftReportService
        result = ShiftReportService.get_dashboard_metrics(branch=self.branch, period='7_days')
        self.assertEqual(result['gross_revenue'], Decimal('2000.00'))

    def test_branch_none_is_system_wide(self):
        self._create_order(
            order_type=Order.OrderType.WALK_IN, status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH, processed_by=self.cashier,
            total=Decimal('300.00'), branch=self.branch,
        )
        self._create_order(
            order_type=Order.OrderType.WALK_IN, status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH, processed_by=self.cashier,
            total=Decimal('700.00'), branch=self.other_branch,
        )
        from reports.shift_services import ShiftReportService
        result = ShiftReportService.get_dashboard_metrics(branch=None, period='7_days')
        self.assertEqual(result['gross_revenue'], Decimal('1000.00'))

    def test_timeline_shape_present(self):
        self._create_order(
            order_type=Order.OrderType.WALK_IN, status=Order.Status.COMPLETED,
            payment_method=Order.PaymentMethod.CASH, processed_by=self.cashier,
            total=Decimal('500.00'),
        )
        from reports.shift_services import ShiftReportService
        result = ShiftReportService.get_dashboard_metrics(branch=self.branch, period='today')
        self.assertEqual(len(result['chart_labels']), len(result['chart_revenue_dataset']))
        self.assertEqual(len(result['chart_labels']), len(result['chart_volume_dataset']))