from django.db import models
from django.conf import settings
from django.utils import timezone


class ScheduledReport(models.Model):
    """A recurring, emailed delivery of a saved :class:`Report`.

    Supports two independent delivery modes that can both be enabled at once:

    * an *aggregated* email of the full result set to a fixed recipient list
      and/or group, and
    * *personalised* slices, where the result set is grouped by a chosen field
      (e.g. the account manager's email) and each group is emailed only its own
      rows.

    The report is executed as ``run_as_user`` so its permission scoping (e.g.
    excluding Protectively Marked jobs) applies - this should be a dedicated
    reporting account rather than a superuser.
    """

    FREQ_DAILY = 'daily'
    FREQ_WEEKLY = 'weekly'
    FREQUENCY_CHOICES = [
        (FREQ_DAILY, 'Daily'),
        (FREQ_WEEKLY, 'Weekly'),
    ]

    DAY_OF_WEEK_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
        (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]

    ATTACHMENT_NONE = ''
    ATTACHMENT_CHOICES = [
        (ATTACHMENT_NONE, 'None'),
        ('csv', 'CSV'),
        ('excel', 'Excel'),
    ]

    name = models.CharField(max_length=255)
    report = models.ForeignKey('Report', on_delete=models.CASCADE, related_name='schedules')
    enabled = models.BooleanField(default=True)

    run_as_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='scheduled_reports',
        help_text="The report runs with this user's permissions. Use a dedicated reporting "
                  "account, not a superuser, so restricted data is not leaked.",
    )

    # Cadence. django_cron has no native "weekly", so the cron runs frequently
    # and is_due() gates on weekday + run_time + last_sent_at.
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default=FREQ_WEEKLY)
    day_of_week = models.PositiveSmallIntegerField(
        choices=DAY_OF_WEEK_CHOICES, null=True, blank=True,
        help_text="Only used for weekly schedules (0=Monday).",
    )
    run_time = models.TimeField(help_text="Earliest local time of day to send.")
    last_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

    # Recipients for the aggregated email.
    send_aggregate_to_group = models.BooleanField(
        default=True, help_text="Send the full report to the recipients below.",
    )
    recipient_emails = models.TextField(
        blank=True, help_text="Comma- or newline-separated email addresses.",
    )
    recipient_group = models.ForeignKey(
        'auth.Group', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_reports',
        help_text="All members of this group also receive the aggregated email.",
    )

    # Personalised slices.
    split_by_field = models.ForeignKey(
        'DataField', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='report_schedules',
        help_text="If set, rows are grouped by this field's value and each value that is a "
                  "valid email address is sent only its own rows (e.g. the account manager email).",
    )

    # Email content / delivery.
    email_subject = models.CharField(max_length=255)
    email_template_slug = models.CharField(
        max_length=255, default='reporting/emails/scheduled_report.html',
        help_text="Template used to render the email body.",
    )
    intro_html = models.TextField(blank=True, help_text="HTML shown above the table.")
    outro_html = models.TextField(blank=True, help_text="HTML shown below the table.")
    attachment_format = models.CharField(
        max_length=10, choices=ATTACHMENT_CHOICES, default=ATTACHMENT_NONE, blank=True,
    )
    filter_overrides = models.JSONField(
        default=dict, blank=True,
        help_text="Runtime values for the report's prompted filters, keyed by filter id.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Scheduled Report'
        verbose_name_plural = 'Scheduled Reports'

    def __str__(self):
        return self.name

    def is_due(self, now=None):
        """Whether this schedule should send at ``now`` (local time)."""
        if not self.enabled:
            return False
        now = now or timezone.localtime()
        # Only send once per calendar day.
        if self.last_sent_at and timezone.localtime(self.last_sent_at).date() >= now.date():
            return False
        # Not yet the configured time of day.
        if now.time() < self.run_time:
            return False
        # Weekly schedules only fire on the chosen weekday.
        if self.frequency == self.FREQ_WEEKLY and self.day_of_week is not None:
            if now.weekday() != self.day_of_week:
                return False
        return True

    def recipient_list(self):
        """Aggregated-email recipients from the free-text list and the group."""
        emails = []
        for chunk in self.recipient_emails.replace('\n', ',').split(','):
            addr = chunk.strip()
            if addr:
                emails.append(addr)
        if self.recipient_group_id:
            for user in self.recipient_group.user_set.all():
                addr = user.email_address() if hasattr(user, 'email_address') else user.email
                if addr:
                    emails.append(addr)
        # De-dupe, preserve order.
        seen = set()
        unique = []
        for addr in emails:
            key = addr.lower()
            if key not in seen:
                seen.add(key)
                unique.append(addr)
        return unique

    def group_rows(self, data):
        """Group result rows by ``split_by_field``'s value.

        Returns an ordered ``{value: [rows]}`` dict. ``data`` rows are the dicts
        produced by ``DataService`` (keyed by field_path). Rows with an empty
        split value are dropped, since there's no-one to send them to.
        """
        if not self.split_by_field_id:
            return {}
        key = self.split_by_field.field_path
        groups = {}
        for row in data:
            value = row.get(key)
            if value in (None, ''):
                continue
            groups.setdefault(value, []).append(row)
        return groups

    def mark_sent(self, now=None):
        self.last_sent_at = now or timezone.now()
        self.save(update_fields=['last_sent_at'])
