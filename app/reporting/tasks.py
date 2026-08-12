import logging
import re
import threading

from django_cron import CronJobBase, Schedule
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import connection
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


# How long the request will wait for an on-screen run to finish inline before
# falling back to the background/polling path (keeps snappy reports instant while
# large ones still can't block past the ALB/nginx idle timeouts).
INLINE_RUN_BUDGET_SECONDS = 12
# A run left 'running' longer than this is presumed dead (crashed worker / killed
# inline thread) and gets re-queued so it can't get stuck forever.
STALE_RUNNING_MINUTES = 15


def process_report_run(run):
    """Compute a report run, persisting rows to the DB and any export file to
    ``default_storage`` (S3 in prod) so results survive across web instances.

    Safe to call from either the cron worker or an inline request thread.
    """
    logger.info(f"Processing report run {run.id} for user {run.user}")
    run.status = ReportRun.STATUS_RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=['status', 'started_at'])

    try:
        rows = DataService.get_report_data(run.report, run.user, run.filter_values or {})
        run.row_count = len(rows)

        # Persist the rows in the DB for the on-screen results page. Any web
        # instance can then render them (no node-local temp file to go missing).
        run.result_json = rows

        # Render a download file too, if this run asked for an export format.
        if run.export_format:
            response = ExportService.export_report(run.report, rows, run.export_format)
            filename = _parse_content_disposition_filename(
                response.get('Content-Disposition', '')
            )
            # Extension is cosmetic (the download name comes from export_filename);
            # derive it from the produced filename, falling back to the format.
            ext = filename.rsplit('.', 1)[-1] if '.' in filename else run.export_format
            key = f"report_runs/{run.id}.{ext}"
            # Overwrite defensively in case a retry produced a stale object.
            if default_storage.exists(key):
                default_storage.delete(key)
            run.export_path = default_storage.save(key, ContentFile(response.content))
            run.export_content_type = response.get('Content-Type', 'application/octet-stream')
            run.export_filename = filename

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
        # Drop any partial rows so a failure while persisting results can't make
        # the FAILED save itself unsaveable (which would leave the run stuck
        # 'running' forever).
        run.result_json = None
        run.save()
        # Single structured event (message + traceback) instead of two
        # separate logger.error calls, which Sentry split into two issues
        # for one failure (CHAOTICA-121/122). logger.exception attaches the
        # active exception's traceback automatically.
        logger.exception(f"Report run {run.id} failed: {e}")


def run_inline_within_budget(run, budget_seconds=INLINE_RUN_BUDGET_SECONDS):
    """Process ``run`` in a worker thread, waiting up to ``budget_seconds``.

    Returns True if it finished within the budget (the request can render the
    results immediately). If it overruns, the thread keeps going to completion in
    the background and the caller falls back to the polling page. Any thread that
    dies mid-run is recovered by ProcessReportRuns' stale-run sweep.

    Assumes autocommit requests (ATOMIC_REQUESTS is not enabled): the caller's
    ReportRun.create() must be committed so the worker thread's own DB connection
    can see it. If ATOMIC_REQUESTS is ever turned on, this fast path must be
    revisited (the run would be invisible to the thread until the request commits).
    """
    def _work():
        try:
            process_report_run(run)
        finally:
            # Threads get their own DB connection; close it so it isn't leaked.
            connection.close()

    thread = threading.Thread(target=_work, name=f"reportrun-{run.id}", daemon=True)
    thread.start()
    thread.join(budget_seconds)
    return not thread.is_alive()


class ProcessReportRuns(CronJobBase):
    """Execute queued report runs out of band.

    Mirrors ``chaotica_utils.tasks.ProcessManualBackupJobs``: pick up one pending
    run, mark it running, compute the rows (and render an export file if the run
    asked for a download), then mark it complete/failed. The browser polls the
    status endpoint meanwhile. On-screen runs are usually processed inline in the
    request; this cron is the reliable fallback and the export/queued-overflow path.
    """

    RUN_EVERY_MINS = 1
    MIN_NUM_FAILURES = 3
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'reporting.process_report_runs'

    def do(self):
        self._requeue_stale_runs()
        pending = ReportRun.objects.filter(status=ReportRun.STATUS_PENDING).order_by('created_at')
        for run in pending[:1]:  # one at a time to avoid overloading the container
            self.process_run(run)

    def _requeue_stale_runs(self):
        """Re-queue runs stuck 'running' past the threshold (dead worker/thread)."""
        cutoff = timezone.now() - timezone.timedelta(minutes=STALE_RUNNING_MINUTES)
        stale = ReportRun.objects.filter(
            status=ReportRun.STATUS_RUNNING, started_at__lt=cutoff
        )
        for run in stale:
            logger.warning(f"Re-queuing stale running report run {run.id}")
            run.status = ReportRun.STATUS_PENDING
            run.started_at = None
            run.save(update_fields=['status', 'started_at'])

    def process_run(self, run):
        process_report_run(run)


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
        # On-screen rows live in run.result_json and go away with the row itself.
        # The export file lives in default_storage (S3 in prod) - remove it.
        if run.export_path:
            try:
                if default_storage.exists(run.export_path):
                    default_storage.delete(run.export_path)
            except Exception as e:
                logger.error(f"Error deleting report export {run.export_path}: {e}")
