import json
import logging
import os
import re
import tempfile

from django_cron import CronJobBase, Schedule
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from constance import config

from chaotica_utils.models import User
from .models import ReportRun, ScheduledReport
from .services.data_service import DataService
from .services.export_service import ExportService

logger = logging.getLogger(__name__)


def _is_valid_email(address):
    try:
        validate_email(address)
        return True
    except ValidationError:
        return False


def _known_user_emails():
    """Lower-cased set of active users' email addresses — the only addresses a
    data-derived split target is allowed to be sent to."""
    emails = set()
    for user in User.objects.filter(is_active=True):
        addr = user.email_address() if hasattr(user, 'email_address') else user.email
        if addr:
            emails.add(addr.strip().lower())
    return emails

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

        # Aggregated email to the fixed (admin-curated) recipient list / group.
        # Drop anything that isn't a well-formed address so a malformed entry
        # can't derail the send.
        if sched.send_aggregate_to_group:
            recipients = [r for r in sched.recipient_list() if _is_valid_email(r)]
            if recipients:
                self._send(sched, recipients, field_names, display_rows(data))

        # Personalised slices - one email per split value. The split key is
        # data-derived, so only deliver to addresses that belong to a known,
        # active internal user (never to an arbitrary value that merely contains
        # '@'), so report data can't be exfiltrated to attacker-controlled rows.
        if split_path:
            allowed = _known_user_emails()
            for value, rows in sched.group_rows(data).items():
                address = str(value).strip()
                if _is_valid_email(address) and address.lower() in allowed:
                    self._send(sched, [address], field_names, display_rows(rows))
                elif address:
                    logger.warning(
                        "Scheduled report '%s': skipping split delivery to "
                        "unrecognised address '%s'.", sched, address,
                    )

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


def _parse_content_disposition_filename(header):
    """Pull the download filename out of a Content-Disposition header, if present."""
    if not header:
        return ''
    match = re.search(r'filename="?([^"]+)"?', header)
    return match.group(1) if match else ''


class ProcessReportRuns(CronJobBase):
    """Execute queued report runs out of band.

    Mirrors ``chaotica_utils.tasks.ProcessManualBackupJobs``: pick up one pending
    run, mark it running, compute the rows (and render an export file if the run
    asked for a download), then mark it complete/failed. The browser polls the
    status endpoint meanwhile.
    """

    RUN_EVERY_MINS = 1
    MIN_NUM_FAILURES = 3
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'reporting.process_report_runs'

    def do(self):
        pending = ReportRun.objects.filter(status=ReportRun.STATUS_PENDING).order_by('created_at')
        for run in pending[:1]:  # one at a time to avoid overloading the container
            self.process_run(run)

    def process_run(self, run):
        logger.info(f"Processing report run {run.id} for user {run.user}")
        run.status = ReportRun.STATUS_RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=['status', 'started_at'])

        try:
            rows = DataService.get_report_data(run.report, run.user, run.filter_values or {})
            run.row_count = len(rows)

            # Persist the rows for the on-screen results page.
            with tempfile.NamedTemporaryFile(
                mode='w', delete=False, suffix='.json', prefix='reportrun_'
            ) as fh:
                json.dump(rows, fh, cls=DjangoJSONEncoder)
                run.result_path = fh.name

            # Render a download file too, if this run asked for an export format.
            if run.export_format:
                response = ExportService.export_report(run.report, rows, run.export_format)
                with tempfile.NamedTemporaryFile(
                    delete=False, prefix='reportexport_'
                ) as fh:
                    fh.write(response.content)
                    run.export_path = fh.name
                run.export_content_type = response.get('Content-Type', 'application/octet-stream')
                run.export_filename = _parse_content_disposition_filename(
                    response.get('Content-Disposition', '')
                )

            run.status = ReportRun.STATUS_COMPLETE
            run.completed_at = timezone.now()
            run.save()

            # last_run_at bookkeeping now happens here rather than in the request.
            run.report.last_run_at = timezone.now()
            run.report.save(update_fields=['last_run_at'])

            logger.info(f"Report run {run.id} completed ({run.row_count} rows)")

        except Exception as e:
            run.status = ReportRun.STATUS_FAILED
            run.error_message = str(e)
            run.completed_at = timezone.now()
            run.save()
            # Single structured event (message + traceback) instead of two
            # separate logger.error calls, which Sentry split into two issues
            # for one failure (CHAOTICA-121/122). logger.exception attaches the
            # active exception's traceback automatically.
            logger.exception(f"Report run {run.id} failed: {e}")


class CleanupOldReportRuns(CronJobBase):
    """Purge finished report runs and their temp files after a grace period."""

    RUN_EVERY_MINS = 60
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'reporting.cleanup_old_report_runs'

    def do(self):
        cutoff = timezone.now() - timezone.timedelta(hours=2)
        old = ReportRun.objects.filter(
            status=ReportRun.STATUS_COMPLETE, completed_at__lt=cutoff
        )
        for run in old:
            self._remove_files(run)
            run.delete()

        old_failed = ReportRun.objects.filter(
            status=ReportRun.STATUS_FAILED,
            completed_at__lt=timezone.now() - timezone.timedelta(hours=24),
        )
        for run in old_failed:
            self._remove_files(run)
            run.delete()

    def _remove_files(self, run):
        for path in (run.result_path, run.export_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as e:
                    logger.error(f"Error deleting report run file {path}: {e}")
