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

    # Saved past a bypassable warning ("Save anyway"): overlap, over scope,
    # framework budget... ``summary`` names what was overridden.
    forced = models.BooleanField(default=False)
    override_reason = models.TextField(default="", blank=True)

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
        """Whether ``user`` may revert this action.

        Site-level ``revert_any_scheduleaction`` holders may always revert.
        Otherwise the user must be the original actor **and** still hold
        ``can_schedule_job`` on the action's scope — reverting recreates / deletes
        / updates the same slots, so it must respect the same object-level
        scheduling permission as a live edit (a user who has since lost
        scheduling rights on a job must not be able to mutate it via undo)."""
        if self.reverted:
            return False
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if user.has_perm("jobtracker.revert_any_scheduleaction"):
            return True
        if not (self.actor_id and self.actor_id == user.pk):
            return False
        return self._user_can_schedule_scope(user)

    def _affected_user_ids(self):
        """User PKs referenced by this action's payload (either before or after)."""
        ids = set()
        for item in self.payload or []:
            for side in ("before", "after"):
                fields = item.get(side) or {}
                uid = fields.get("user_id")
                if uid:
                    ids.add(uid)
        return ids

    def _user_can_schedule_scope(self, user):
        """Whether ``user`` currently holds ``can_schedule_job`` on the unit(s)
        this action touches: the job's unit for job/phase-scoped actions, or each
        affected user's unit(s) for user-owned (project/internal/comment) actions.

        When no governing unit can be resolved (a unit-less job, or an affected
        user with no current unit memberships), revert still requires the user to
        hold ``can_schedule_job`` on *some* unit — being the action's own actor is
        not, on its own, enough. Only genuine schedulers may revert a change; an
        ordinary user with no scheduling rights never can. (The live-edit paths
        reach the same bar via the ``can_schedule_job`` decorator on every
        mutating endpoint; revert has no such decorator, so the floor is enforced
        here.)"""
        from ..utils import user_has_unit_perms

        perm = "jobtracker.can_schedule_job"
        job = None
        if self.job_id:
            job = self.job
        elif self.phase_id:
            job = self.phase.job
        if job is not None:
            if job.unit:
                return user.has_perm(perm, job.unit)
            # Unit-less job: fall back to needing scheduling rights somewhere.
            return user_has_unit_perms(user, perm)
        # User-owned action — check each affected user's units.
        from chaotica_utils.models import User

        resolved_a_unit = False
        for resource in User.objects.filter(pk__in=self._affected_user_ids()):
            units = [
                m.unit for m in resource.unit_memberships.select_related("unit").all()
            ]
            if units:
                resolved_a_unit = True
                if not any(user.has_perm(perm, u) for u in units):
                    return False
        if resolved_a_unit:
            return True
        # No governing unit anywhere: require scheduling rights somewhere.
        return user_has_unit_perms(user, perm)
