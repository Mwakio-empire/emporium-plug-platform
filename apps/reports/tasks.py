import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from .document_generators import OperationsReportPDFGenerator
from .models import ScheduledReport, ScheduledReportDelivery
from .operations_services import OperationsReportService


logger = logging.getLogger(__name__)


def report_period(frequency, today):
    if frequency == ScheduledReport.Frequency.DAILY:
        day = today - timedelta(days=1)
        return day, day
    if frequency == ScheduledReport.Frequency.WEEKLY:
        end = today - timedelta(days=today.weekday() + 1)
        return end - timedelta(days=6), end
    if frequency == ScheduledReport.Frequency.MONTHLY:
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    raise ValueError('Unsupported scheduled-report frequency.')


def next_run_after(current, frequency):
    if frequency == ScheduledReport.Frequency.DAILY:
        return current + timedelta(days=1)
    if frequency == ScheduledReport.Frequency.WEEKLY:
        return current + timedelta(days=7)
    if frequency == ScheduledReport.Frequency.MONTHLY:
        first_next = (current.date().replace(day=1) + timedelta(days=32)).replace(day=1)
        return current.replace(year=first_next.year, month=first_next.month, day=1)
    raise ValueError('Unsupported scheduled-report frequency.')


@shared_task
def dispatch_due_scheduled_reports():
    """Queue each due configuration independently so one failure cannot block others."""
    schedule_ids = list(ScheduledReport.objects.filter(
        is_active=True, next_run_at__lte=timezone.now(),
    ).values_list('id', flat=True))
    for schedule_id in schedule_ids:
        send_scheduled_report.delay(schedule_id)
    return len(schedule_ids)


@shared_task
def send_scheduled_report(schedule_id):
    """
    Send one configured report once for its reporting period.

    Failed deliveries are retained for manual follow-up and are not automatically
    resent, avoiding duplicate email after an ambiguous provider response.
    """
    now = timezone.now()
    with transaction.atomic():
        try:
            schedule = ScheduledReport.objects.select_for_update().select_related(
                'branch',
            ).get(pk=schedule_id, is_active=True)
        except ScheduledReport.DoesNotExist:
            return False
        if schedule.next_run_at > now:
            return False
        period_start, period_end = report_period(
            schedule.frequency, timezone.localdate(now),
        )
        delivery, created = ScheduledReportDelivery.objects.get_or_create(
            schedule=schedule,
            period_start=period_start,
            period_end=period_end,
            defaults={'status': ScheduledReportDelivery.Status.FAILED},
        )
        if not created and delivery.status == ScheduledReportDelivery.Status.SENT:
            schedule.next_run_at = next_run_after(schedule.next_run_at, schedule.frequency)
            schedule.save(update_fields=['next_run_at'])
            return True

    report = OperationsReportService.compile(
        start_date=period_start, end_date=period_end, branch=schedule.branch,
    )
    pdf = OperationsReportPDFGenerator.compile(report)
    email = EmailMessage(
        subject=f'Emporium Plug {schedule.get_frequency_display()} operations report',
        body=(
            f"Attached is the configured operations report for {period_start} to {period_end}.\n\n"
            "Revenue and return definitions are printed inside the report."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[schedule.recipient_email],
    )
    email.attach(
        filename=f'emporium-operations-{period_start}-{period_end}.pdf',
        content=pdf.getvalue(),
        mimetype='application/pdf',
    )
    try:
        email.send(fail_silently=False)
    except Exception as exc:
        logger.warning(
            'Scheduled report delivery failed | schedule_id=%s | exception=%s',
            schedule_id, type(exc).__name__,
        )
        with transaction.atomic():
            delivery = ScheduledReportDelivery.objects.select_for_update().get(pk=delivery.pk)
            delivery.status = ScheduledReportDelivery.Status.FAILED
            delivery.error_summary = type(exc).__name__[:500]
            delivery.save(update_fields=['status', 'error_summary'])
            schedule = ScheduledReport.objects.select_for_update().get(pk=schedule_id)
            schedule.next_run_at = next_run_after(schedule.next_run_at, schedule.frequency)
            schedule.save(update_fields=['next_run_at'])
        return False

    with transaction.atomic():
        delivery = ScheduledReportDelivery.objects.select_for_update().get(pk=delivery.pk)
        delivery.status = ScheduledReportDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        delivery.error_summary = ''
        delivery.save(update_fields=['status', 'sent_at', 'error_summary'])
        schedule = ScheduledReport.objects.select_for_update().get(pk=schedule_id)
        schedule.last_sent_at = delivery.sent_at
        schedule.next_run_at = next_run_after(schedule.next_run_at, schedule.frequency)
        schedule.save(update_fields=['last_sent_at', 'next_run_at'])
    return True
