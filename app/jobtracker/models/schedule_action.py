from django.db import models
from django.conf import settings


class ScheduleActionType(models.TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    MOVE = "MOVE", "Move"
    CLEAR = "CLEAR", "Clear"
    BATCH = "BATCH", "Batch"
    REVERT = "REVERT", "Revert"


class ScheduleAction(models.Model):
    """A single logical, revertable, broadcastable unit of scheduler change.

    Every scheduler mutation emits one ScheduleAction carrying enough before/after
    data (in ``payload``) to reverse itself. This is the shared primitive behind
    both the version-control (undo/revert) history and the live async delta layer.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="schedule_actions",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created = models.DateTimeField(auto_now_add=True)
    action_type = models.CharField(
        max_length=16, choices=ScheduleActionType.choices
    )

    # Scope for the history-panel filter. Both null ⇒ a global-only action.
    job = models.ForeignKey(
        "jobtracker.Job",
        related_name="schedule_actions",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    phase = models.ForeignKey(
        "jobtracker.Phase",
        related_name="schedule_actions",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    summary = models.TextField(default="", blank=True)

    # List of per-item snapshots:
    #   {"model": "timeslot"|"timeslotcomment", "pk": N,
    #    "before": {...}|null, "after": {...}|null}
    # before=null ⇒ create; after=null ⇒ delete; both present ⇒ update.
    payload = models.JSONField(default=list)

    reverted = models.BooleanField(default=False)
    reverted_by = models.ForeignKey(
        "self",
        related_name="reverts",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ["-created"]
        permissions = [
            ("revert_any_scheduleaction", "Can revert any schedule change"),
        ]

    def __str__(self):
        return "{} by {} @ {}".format(
            self.get_action_type_display(),
            self.actor or "system",
            self.created,
        )

    def can_revert(self, user):
        """Whether ``user`` may revert this action: their own & not yet reverted,
        or they hold the site-level revert-any permission."""
        if self.reverted:
            return False
        if self.action_type == ScheduleActionType.REVERT:
            # A revert is itself revertable (redo) under the same rules.
            pass
        if self.actor_id and self.actor_id == user.pk:
            return True
        return user.has_perm("jobtracker.revert_any_scheduleaction")
