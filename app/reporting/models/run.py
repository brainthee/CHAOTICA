import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from .report import Report


class ReportRun(models.Model):
    """A single queued/background execution of a report.

    Running a large report synchronously in the request blocks past the ALB /
    nginx idle timeouts. Instead the view creates a pending ``ReportRun``; the
    ``reporting.tasks.ProcessReportRuns`` cron (mirrors
    ``chaotica_utils.tasks.ProcessManualBackupJobs``) executes it out of band and
    the browser polls the status endpoint until it is ready.
    """

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETE = 'complete'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='runs')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='report_runs'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # Runtime filter values keyed by filter id (as strings), as collected by the view.
    filter_values = models.JSONField(default=dict, blank=True)
    # None => on-screen HTML results. Otherwise one of Report.PRESENTATION_CHOICES => a download.
    export_format = models.CharField(max_length=50, blank=True, null=True)

    # Computed rows for the on-screen results page, persisted in the DB so any
    # web instance can render them (node-local temp files broke across the
    # multi-instance load balancer - a poll could land on an instance that never
    # wrote the file). result_path is retained only for backwards compatibility.
    # DjangoJSONEncoder so report rows containing dates / datetimes / Decimals
    # (which the plain stdlib JSON encoder can't serialize) persist correctly.
    result_json = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    result_path = models.CharField(max_length=500, blank=True)
    row_count = models.IntegerField(null=True, blank=True)
    # Rendered export file (when export_format is set) plus how to serve it back.
    # export_path holds a key into default_storage (S3 in prod), not a local path.
    export_path = models.CharField(max_length=500, blank=True)
    export_content_type = models.CharField(max_length=255, blank=True)
    export_filename = models.CharField(max_length=255, blank=True)

    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Run {self.id} of {self.report_id} ({self.status})"

    @property
    def is_export(self):
        return bool(self.export_format)
