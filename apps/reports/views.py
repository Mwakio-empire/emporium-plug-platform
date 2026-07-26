# apps/reports/views.py

import csv
from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from branches.models import Branch
from users.models import User
from users.permissions import IsBranchManagerOrAbove, IsStaffOrAbove

from .operations_services import OperationsReportService
from .shift_services import ShiftReportService


def _parse_period_params(request):
    """
    Shared helper. Reads ?period= and optional ?start= ?end= from query params.
    Returns (period, custom_start, custom_end).
    custom_start/custom_end are date objects or None.
    """
    period = request.query_params.get('period', 'today')
    custom_start = custom_end = None

    if period == 'custom':
        start_str = request.query_params.get('start')
        end_str = request.query_params.get('end')
        try:
            custom_start = date.fromisoformat(start_str) if start_str else None
            custom_end = date.fromisoformat(end_str) if end_str else None
        except ValueError:
            return period, None, None, 'start and end must be in YYYY-MM-DD format.'

    return period, custom_start, custom_end, None


class MyShiftReportView(APIView):
    """
    GET /api/reports/my-shift/
    Any authenticated staff member views their own shift summary.

    Query params:
        ?period=today          (default)
        ?period=yesterday
        ?period=last_week
        ?period=last_month
        ?period=custom&start=YYYY-MM-DD&end=YYYY-MM-DD
    """
    permission_classes = [IsStaffOrAbove]

    def get(self, request):
        period, custom_start, custom_end, err = _parse_period_params(request)
        if err:
            return Response({'error': err}, status=400)

        if period == 'custom' and not (custom_start and custom_end):
            return Response(
                {'error': 'start and end are required for custom period (YYYY-MM-DD).'},
                status=400,
            )

        try:
            summary = ShiftReportService.get_shift_summary(
                staff_user=request.user,
                period=period,
                custom_start=custom_start,
                custom_end=custom_end,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        return Response(summary)


class BranchDailySummaryView(APIView):
    """
    GET /api/reports/branch-daily/
    Branch manager views full branch summary.

    Query params: same as MyShiftReportView.
    """
    permission_classes = [IsBranchManagerOrAbove]

    def get(self, request):
        if not request.user.branch:
            return Response(
                {'error': 'You are not assigned to a branch.'},
                status=400,
            )

        period, custom_start, custom_end, err = _parse_period_params(request)
        if err:
            return Response({'error': err}, status=400)

        if period == 'custom' and not (custom_start and custom_end):
            return Response(
                {'error': 'start and end are required for custom period (YYYY-MM-DD).'},
                status=400,
            )

        try:
            summary = ShiftReportService.get_branch_daily_summary(
                branch=request.user.branch,
                period=period,
                custom_start=custom_start,
                custom_end=custom_end,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        return Response(summary)


def _operations_params(request):
    today = date.today()
    start_text = request.GET.get('start') or (today - timedelta(days=29)).isoformat()
    end_text = request.GET.get('end') or today.isoformat()
    try:
        start_date = date.fromisoformat(start_text)
        end_date = date.fromisoformat(end_text)
    except ValueError as exc:
        raise ValueError('start and end must use YYYY-MM-DD format.') from exc

    user = request.user
    requested_branch = request.GET.get('branch', '').strip()
    if user.role == User.Role.SUPER_ADMIN:
        if requested_branch and requested_branch.lower() != 'all':
            try:
                branch = Branch.objects.get(pk=int(requested_branch))
            except (Branch.DoesNotExist, TypeError, ValueError) as exc:
                raise ValueError('The selected branch does not exist.') from exc
        else:
            branch = None
    else:
        if user.branch_id is None:
            raise PermissionError('A branch manager must be assigned to a branch.')
        if requested_branch and requested_branch.lower() != 'all':
            try:
                requested_id = int(requested_branch)
            except ValueError as exc:
                raise ValueError('The selected branch does not exist.') from exc
            if requested_id != user.branch_id:
                raise PermissionError('Branch managers may report only on their assigned branch.')
        branch = user.branch
    return start_date, end_date, branch


class OperationsReportView(APIView):
    permission_classes = [IsBranchManagerOrAbove]

    def get(self, request):
        try:
            start_date, end_date, branch = _operations_params(request)
            report = OperationsReportService.compile(
                start_date=start_date, end_date=end_date, branch=branch,
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(report)


class OperationsReportWorkspaceView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_active and self.request.user.role in {
            User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN,
        }

    def get(self, request):
        try:
            start_date, end_date, branch = _operations_params(request)
            report = OperationsReportService.compile(
                start_date=start_date, end_date=end_date, branch=branch,
            )
        except (ValueError, PermissionError) as exc:
            return render(request, 'reports/operations.html', {
                'report_error': str(exc), 'branches': Branch.objects.order_by('name'),
            }, status=400 if isinstance(exc, ValueError) else 403)
        return render(request, 'reports/operations.html', {
            'report': report,
            'branches': Branch.objects.order_by('name'),
            'selected_branch': branch,
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        })


class OperationsReportCSVView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_active and self.request.user.role in {
            User.Role.BRANCH_MANAGER, User.Role.SUPER_ADMIN,
        }

    def get(self, request):
        try:
            start_date, end_date, branch = _operations_params(request)
            report = OperationsReportService.compile(
                start_date=start_date, end_date=end_date, branch=branch,
            )
        except ValueError as exc:
            return HttpResponse(str(exc), status=400, content_type='text/plain')
        except PermissionError as exc:
            return HttpResponse(str(exc), status=403, content_type='text/plain')

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="operations-{start_date}-{end_date}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(['Emporium Plug operations report'])
        writer.writerow(['Branch', report['definition']['branch']])
        writer.writerow(['Period', start_date.isoformat(), end_date.isoformat()])
        writer.writerow(['Revenue definition', report['definition']['revenue_basis']])
        writer.writerow([])
        writer.writerow(['Metric', 'Value'])
        for label, key in (
            ('Recognized revenue (KES)', 'revenue'),
            ('Orders', 'orders'),
            ('Discounts (KES)', 'discounts'),
            ('Delivery fees (KES)', 'delivery_fees'),
            ('Average order (KES)', 'average_order'),
        ):
            writer.writerow([label, report['sales'][key]])
        writer.writerow([])
        writer.writerow(['Payment method', 'Orders', 'Amount (KES)'])
        for row in report['sales']['payment_breakdown']:
            writer.writerow([row['payment_method'], row['order_count'], row['amount']])
        writer.writerow([])
        writer.writerow(['Product', 'SKU', 'Units', 'Sales (KES)'])
        for row in report['products']:
            writer.writerow([row['name'], row['sku'], row['units'], row['amount']])
        return response
