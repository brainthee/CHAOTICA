import logging

from django_cron import CronJobBase, Schedule
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from constance import config

from .models import ScheduledReport
from .services.data_service import DataService
from .services.export_service import ExportService

logger = logging.getLogger(__name__)

_ATTACHMENT_META = {
    'csv': ('text/csv', 'csv'),
    'excel': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'),
}


class task_send_scheduled_reports(CronJobBase):
    """Send any due scheduled reports.

    Runs frequently; ScheduledReport.is_due() gates the actual cadence
    (weekday / time-of-day) and prevents duplicate sends within a day.
    """

    RUN_EVERY_MINS = 15
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'reporting.task_send_scheduled_reports'

    def do(self):
        now = timezone.localtime()
        schedules = ScheduledReport.objects.filter(enabled=True).select_related(
            'report', 'run_as_user', 'split_by_field', 'recipient_group'
        )
        for sched in schedules:
            if not sched.is_due(now):
                continue
            try:
                self._process(sched)
                sched.mark_sent()
            except Exception as e:
                logger.error(f"Failed to send scheduled report '{sched}': {e}", exc_info=True)

    def _process(self, sched):
        report = sched.report
        report_fields = list(report.get_fields())
        display_paths = [f.data_field.field_path for f in report_fields]
        field_names = [f.get_display_name() for f in report_fields]

        # The split key may not be a displayed column - fetch it as a hidden extra.
        split_path = sched.split_by_field.field_path if sched.split_by_field_id else None
        extra = [split_path] if split_path and split_path not in display_paths else []

        data = DataService.get_report_data(
            report, sched.run_as_user, sched.filter_overrides, extra_field_paths=extra
        )

        def display_rows(rows):
            # Project to display columns only, in order, so hidden extras don't
            # leak into the rendered table.
            return [{path: row.get(path) for path in display_paths} for row in rows]

        # Aggregated email to the fixed recipient list / group.
        if sched.send_aggregate_to_group:
            recipients = sched.recipient_list()
            if recipients:
                self._send(sched, recipients, field_names, display_rows(data))

        # Personalised slices - one email per split value that is a valid address.
        if split_path:
            for value, rows in sched.group_rows(data).items():
                address = str(value).strip()
                if '@' in address:
                    self._send(sched, [address], field_names, display_rows(rows))

    def _send(self, sched, recipients, field_names, rows):
        if not config.EMAIL_ENABLED:
            logger.info(f"EMAIL_ENABLED is off - skipping scheduled report '{sched}'.")
            return

        context = {
            'title': sched.email_subject,
            'intro_html': sched.intro_html,
            'outro_html': sched.outro_html,
            'field_names': field_names,
            'rows': rows,
            'report': sched.report,
            'action_link': f"{settings.SITE_PROTO}://{settings.SITE_DOMAIN}{sched.report.run_url()}",
            'SITE_DOMAIN': settings.SITE_DOMAIN,
            'SITE_PROTO': settings.SITE_PROTO,
            'generated_at': timezone.localtime().strftime('%Y-%m-%d %H:%M'),
        }
        html = render_to_string(sched.email_template_slug, context)

        email = EmailMultiAlternatives(
            subject=sched.email_subject,
            body=strip_tags(html),
            from_email=None,  # falls back to DEFAULT_FROM_EMAIL
            to=recipients,
        )
        email.attach_alternative(html, 'text/html')
        self._maybe_attach(sched, rows, email)
        email.send(fail_silently=False)

    def _maybe_attach(self, sched, rows, email):
        meta = _ATTACHMENT_META.get(sched.attachment_format)
        if not meta:
            return
        mimetype, ext = meta
        try:
            response = ExportService.export_report(sched.report, rows, sched.attachment_format)
            filename = f"{sched.report.name}.{ext}"
            email.attach(filename, response.content, mimetype)
        except Exception as e:
            logger.error(f"Failed to build {sched.attachment_format} attachment for '{sched}': {e}")
