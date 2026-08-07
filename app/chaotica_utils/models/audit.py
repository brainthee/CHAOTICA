from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from ..utils import get_sentinel_user


class AuditVerb(models.TextChoices):
    CREATE = "create", "Created"
    UPDATE = "update", "Updated"
    DELETE = "delete", "Deleted"
    STATUS_CHANGE = "status_change", "Status Changed"
    ASSIGN = "assign", "Assigned"
    UNASSIGN = "unassign", "Unassigned"
    SCHEDULE = "schedule", "Scheduled"
    LOGIN = "login", "Logged In"
    LOGOUT = "logout", "Logged Out"
    LOGIN_FAILED = "login_failed", "Login Failed"
    PERMISSION_CHANGE = "permission_change", "Permissions Changed"
    TOKEN_ISSUED = "token_issued", "Token Issued"
    TOKEN_REVOKED = "token_revoked", "Token Revoked"
    SYNC = "sync", "Synchronised"
    EXPORT = "export", "Exported"
    COMMENT = "comment", "Commented"
    LINK_ADD = "link_add", "Link Added"
    LINK_REMOVE = "link_remove", "Link Removed"
    OTHER = "other", "Activity"


class AuditCategory(models.TextChoices):
    GENERAL = "general", "General"
    AUTH = "auth", "Authentication"
    SECURITY = "security", "Security"
    FINANCE = "finance", "Finance"
    CONFIG = "config", "Configuration"
    SCHEDULE = "schedule", "Schedule"
    WORKFLOW = "workflow", "Workflow"


# Categories only global admins may see, even on an object's own activity tab.
SENSITIVE_CATEGORIES = (
    AuditCategory.AUTH,
    AuditCategory.SECURITY,
    AuditCategory.FINANCE,
)


class AuditSource(models.TextChoices):
    WEB = "web", "Web"
    API = "api", "API"
    CELERY = "celery", "Background Task"
    SYSTEM = "system", "System"
    RM_SYNC = "rm_sync", "Resource Manager Sync"
    CLI = "cli", "Command Line"


class AuditSeverity(models.IntegerChoices):
    INFO = 20, "Info"
    NOTICE = 25, "Notice"
    WARNING = 30, "Warning"
    ERROR = 40, "Error"


class AuditEvent(models.Model):
    """Append-only, centralised record of "who did what, to what, when".

    Complements ``simple_history`` (full field snapshots per model) and
    ``ScheduleAction`` (reversible scheduler commit log). This model is the
    single sink queried for object-level activity tabs and the site-wide feed.
    Never attach ``HistoricalRecords`` to it — it is immutable by design.
    """

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET(get_sentinel_user),
        related_name="audit_events",
        help_text="User who performed the action. Null means the SYSTEM acted.",
    )
    # Denormalised display string captured at write time so the read path never
    # joins to (a possibly deleted/renamed) user.
    actor_repr = models.CharField(max_length=255, blank=True)

    verb = models.CharField(max_length=32, choices=AuditVerb.choices)
    category = models.CharField(
        max_length=24,
        choices=AuditCategory.choices,
        default=AuditCategory.GENERAL,
        db_index=True,
    )
    message = models.TextField(blank=True)

    target_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL
    )
    # CharField (not int) so UUID PKs and non-integer keys are supported.
    target_id = models.CharField(max_length=64, null=True, blank=True)
    target = GenericForeignKey("target_content_type", "target_id")
    # Denormalised target label so the site-wide feed renders without
    # dereferencing (possibly deleted) targets.
    target_repr = models.CharField(max_length=255, blank=True)

    source = models.CharField(
        max_length=16, choices=AuditSource.choices, default=AuditSource.WEB
    )
    severity = models.PositiveSmallIntegerField(
        choices=AuditSeverity.choices, default=AuditSeverity.INFO
    )

    # Compact, diff-only: {"field": [old, new]}. Full snapshots are the job of
    # simple_history, so we deliberately do not duplicate them here.
    changes = models.JSONField(null=True, blank=True)
    # Request/context extras: ip, path, request_id, etc.
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(
                fields=["target_content_type", "target_id", "-timestamp"],
                name="audit_target_idx",
            ),
            models.Index(fields=["category", "-timestamp"], name="audit_category_idx"),
            models.Index(fields=["actor", "-timestamp"], name="audit_actor_idx"),
        ]

    def __str__(self):
        who = self.actor_repr or "SYSTEM"
        return f"{who} {self.get_verb_display()} {self.target_repr}".strip()

    # --- Compatibility aliases -------------------------------------------------
    # Let the existing ``partials/activity.html`` render an AuditEvent queryset
    # unchanged (it reads ``.content``, ``.create_date``, ``.author``,
    # ``.is_system_note``).
    @property
    def content(self):
        return self.message

    @property
    def create_date(self):
        return self.timestamp

    @property
    def author(self):
        return self.actor

    @property
    def is_system_note(self):
        return self.actor_id is None

    @property
    def is_sensitive(self):
        return self.category in SENSITIVE_CATEGORIES
