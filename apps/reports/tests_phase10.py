from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from branches.models import Branch
from catalog.models import Category, Product
from inventory.models import Stock
from orders.models import Order, OrderItem, OrderStatusHistory
from reports.models import ScheduledReport, ScheduledReportDelivery
from reports.operations_services import OperationsReportService
from reports.tasks import dispatch_due_scheduled_reports, send_scheduled_report
from users.models import User


class Phase10ReportTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='S18 Report Branch', location='Nairobi')
        self.other_branch = Branch.objects.create(name='OTC Report Branch', location='Nairobi')
        self.manager = User.objects.create_user(
            username='reportmanager', phone_number='+254700992001',
            email='reportmanager@example.test', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.branch,
        )
        self.other_manager = User.objects.create_user(
            username='otherreportmanager', phone_number='+254700992002',
            email='otherreportmanager@example.test', password='StrongPass123!',
            role=User.Role.BRANCH_MANAGER, branch=self.other_branch,
        )
        self.super_admin = User.objects.create_user(
            username='reportsuper', phone_number='+254700992003',
            email='reportsuper@example.test', password='StrongPass123!',
            role=User.Role.SUPER_ADMIN,
        )
        category = Category.objects.create(name='Phase 10', slug='phase-10')
        self.product = Product.objects.create(
            name='Report Kettle', slug='report-kettle', category=category,
            price=Decimal('1000.00'),
        )
        self.slow_product = Product.objects.create(
            name='Slow Radio', slug='slow-radio', category=category,
            price=Decimal('500.00'),
        )
        Stock.objects.create(branch=self.branch, product=self.product, quantity=8, reserved_quantity=2)
        Stock.objects.create(branch=self.branch, product=self.slow_product, quantity=4)

    def order(self, *, branch=None, status=Order.Status.COMPLETED, total='1000.00', order_type=Order.OrderType.WALK_IN):
        order = Order.objects.create(
            branch=branch or self.branch,
            order_type=order_type,
            customer_phone='+254711000000',
            processed_by=self.manager if (branch or self.branch) == self.branch else self.other_manager,
            payment_method=Order.PaymentMethod.CASH,
            status=status,
            subtotal=Decimal(total), total_payable=Decimal(total),
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=1,
            unit_price=Decimal(total),
        )
        return order

    def report(self, branch=None):
        today = timezone.localdate()
        return OperationsReportService.compile(
            start_date=today, end_date=today, branch=branch,
        )

    def test_revenue_reconciles_to_recognized_current_statuses(self):
        self.order(status=Order.Status.COMPLETED, total='1000.00')
        confirmed = self.order(
            status=Order.Status.CUSTOMER_CONFIRMED, total='2000.00',
            order_type=Order.OrderType.ONLINE_DELIVERY,
        )
        OrderStatusHistory.objects.create(
            order=confirmed, old_status=Order.Status.DELIVERED,
            new_status=Order.Status.CUSTOMER_CONFIRMED,
            changed_by=self.manager,
        )
        self.order(status=Order.Status.PENDING, total='9000.00')
        self.order(status=Order.Status.DISPUTED, total='8000.00')
        self.order(status=Order.Status.VOIDED, total='7000.00')

        report = self.report(self.branch)
        self.assertEqual(report['sales']['revenue'], Decimal('3000.00'))
        self.assertEqual(report['sales']['orders'], 2)
        self.assertEqual(sum(row['amount'] for row in report['sales']['payment_breakdown']), Decimal('3000.00'))

    def test_recognition_uses_success_transition_date_not_order_creation_date(self):
        order = self.order(
            status=Order.Status.COLLECTED, total='1500.00',
            order_type=Order.OrderType.ONLINE_PICKUP,
        )
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=20),
        )
        OrderStatusHistory.objects.create(
            order=order, old_status=Order.Status.READY_FOR_PICKUP,
            new_status=Order.Status.COLLECTED, changed_by=self.manager,
        )
        self.assertEqual(self.report(self.branch)['sales']['revenue'], Decimal('1500.00'))

    def test_inventory_and_dead_stock_reconcile(self):
        self.order(total='1000.00')
        report = self.report(self.branch)
        self.assertEqual(report['inventory']['on_hand'], 12)
        self.assertEqual(report['inventory']['reserved'], 2)
        self.assertEqual(report['inventory']['available'], 10)
        self.assertEqual(
            [row['name'] for row in report['inventory']['slow_or_dead_stock']],
            ['Slow Radio'],
        )

    def test_branch_manager_api_is_forced_to_own_branch(self):
        self.order(total='1000.00')
        self.order(branch=self.other_branch, total='5000.00')
        self.client.force_login(self.manager)
        response = self.client.get(reverse('reports:operations'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data['sales']['revenue']), Decimal('1000.00'))
        denied = self.client.get(reverse('reports:operations'), {'branch': self.other_branch.pk})
        self.assertEqual(denied.status_code, 403)

    def test_super_admin_can_compare_all_branches(self):
        self.order(total='1000.00')
        self.order(branch=self.other_branch, total='5000.00')
        self.client.force_login(self.super_admin)
        response = self.client.get(reverse('reports:operations'), {'branch': 'all'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data['sales']['revenue']), Decimal('6000.00'))
        self.assertEqual(len(response.data['sales']['branch_breakdown']), 2)

    def test_date_validation_and_range_limit(self):
        self.client.force_login(self.manager)
        url = reverse('reports:operations')
        self.assertEqual(self.client.get(url, {'start': 'bad', 'end': '2026-01-01'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'start': '2026-01-02', 'end': '2026-01-01'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'start': '2024-01-01', 'end': '2026-01-01'}).status_code, 400)

    def test_workspace_and_csv_are_manager_authorized(self):
        self.order(total='1000.00')
        self.client.force_login(self.manager)
        page = self.client.get(reverse('report_workspace:operations'))
        self.assertContains(page, 'Operations reports')
        self.assertContains(page, 'KES 1000.00')
        export = self.client.get(reverse('report_workspace:operations-csv'))
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn(b'Recognized revenue', export.content)

    def test_staff_cannot_access_management_reports(self):
        staff = User.objects.create_user(
            username='reportstaff', phone_number='+254700992004',
            email='reportstaff@example.test', password='StrongPass123!',
            role=User.Role.STAFF, branch=self.branch,
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('reports:operations')).status_code, 403)
        self.assertEqual(self.client.get(reverse('report_workspace:operations')).status_code, 403)

    def schedule(self, *, frequency=ScheduledReport.Frequency.DAILY):
        return ScheduledReport.objects.create(
            name='Daily branch report', frequency=frequency,
            branch=self.branch, recipient_email='owner@example.test',
            next_run_at=timezone.now() - timedelta(minutes=1),
            created_by=self.super_admin,
        )

    def test_scheduled_report_sends_verified_pdf_once(self):
        self.order(total='1000.00')
        schedule = self.schedule()
        self.assertTrue(send_scheduled_report(schedule.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@example.test'])
        filename, content, mimetype = mail.outbox[0].attachments[0]
        self.assertEqual(mimetype, 'application/pdf')
        self.assertTrue(content.startswith(b'%PDF'))
        delivery = ScheduledReportDelivery.objects.get(schedule=schedule)
        self.assertEqual(delivery.status, ScheduledReportDelivery.Status.SENT)
        schedule.refresh_from_db()
        self.assertIsNotNone(schedule.last_sent_at)
        self.assertFalse(send_scheduled_report(schedule.pk))
        self.assertEqual(len(mail.outbox), 1)

    @patch('reports.tasks.EmailMessage.send', side_effect=RuntimeError('provider unavailable'))
    def test_scheduled_report_failure_is_recorded_without_blind_retry(self, mocked_send):
        schedule = self.schedule()
        self.assertFalse(send_scheduled_report(schedule.pk))
        delivery = ScheduledReportDelivery.objects.get(schedule=schedule)
        self.assertEqual(delivery.status, ScheduledReportDelivery.Status.FAILED)
        self.assertEqual(delivery.error_summary, 'RuntimeError')
        schedule.refresh_from_db()
        self.assertGreater(schedule.next_run_at, timezone.now())

    @patch('reports.tasks.send_scheduled_report.delay')
    def test_dispatcher_queues_only_due_active_schedules(self, mocked_delay):
        due = self.schedule()
        ScheduledReport.objects.create(
            name='Inactive', frequency=ScheduledReport.Frequency.DAILY,
            branch=self.branch, recipient_email='inactive@example.test',
            next_run_at=timezone.now() - timedelta(minutes=1),
            created_by=self.super_admin, is_active=False,
        )
        self.assertEqual(dispatch_due_scheduled_reports(), 1)
        mocked_delay.assert_called_once_with(due.pk)
