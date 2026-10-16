"""Policy facade: one place that answers "may this user …?" for the API.

Every rule delegates to the code the UI already uses (guardian unit perms, the
``*_or_403`` decorators' cascade, the model managers, ``utils`` helpers), so
the API and the templates cannot disagree. A :class:`PolicyContext` is built
once per request and memoises the per-permission unit lookups that dashboard,
alarms and entropy otherwise repeat.

This is the seam for a future policy decision point (Lambda #58): callers ask
``policy.can(action, obj)`` / ``policy.scope(action, qs)``, never guardian.
"""

from django.db.models import Q
from django.utils.functional import cached_property
from guardian.shortcuts import get_objects_for_user


def _codename(perm):
    return perm.rsplit(".", 1)[-1]


class PolicyContext:
    def __init__(self, user):
        self.user = user
        self._unit_qs = {}
        self._unit_ids = {}
        self._bools = {}

    # -- unit permission memo ------------------------------------------------

    def units(self, perm):
        """Units on which the user holds ``perm`` (unevaluated queryset)."""
        from .models import OrganisationalUnit

        key = _codename(perm)
        if key not in self._unit_qs:
            self._unit_qs[key] = get_objects_for_user(
                self.user, perm, klass=OrganisationalUnit
            )
        return self._unit_qs[key]

    def unit_ids(self, perm):
        key = _codename(perm)
        if key not in self._unit_ids:
            self._unit_ids[key] = frozenset(
                self.units(perm).values_list("pk", flat=True)
            )
        return self._unit_ids[key]

    def has_any_unit_perm(self, perm):
        return bool(self.unit_ids(perm))

    @cached_property
    def member_unit_ids(self):
        from .models import OrganisationalUnit

        return frozenset(
            OrganisationalUnit.objects.filter(
                members__member=self.user, members__left_date__isnull=True
            ).values_list("pk", flat=True)
        )

    def _memo(self, key, fn):
        if key not in self._bools:
            self._bools[key] = fn()
        return self._bools[key]

    # -- object checks -------------------------------------------------------

    def job_perm(self, perm, obj):
        """The ``job_permission_required_or_403`` test: unit/object perm, else
        the job team's guest perms."""
        from .enums import JobGuestPermissions
        from .models import Job, Phase
        from .utils import user_has_unit_perms

        if not self.user.is_authenticated:
            return False
        if user_has_unit_perms(self.user, [perm], obj=obj):
            return True
        job = (
            obj if isinstance(obj, Job) else obj.job if isinstance(obj, Phase) else None
        )
        return job is not None and JobGuestPermissions.permits(self.user, job, [perm])

    def can(self, action, obj=None):
        try:
            rule = _CAN[action]
        except KeyError:
            raise KeyError(f"Unknown policy action {action!r}")
        return bool(rule(self, obj))

    def scope(self, action, queryset):
        try:
            rule = _SCOPE[action]
        except KeyError:
            raise KeyError(f"Unknown policy scope {action!r}")
        return rule(self, queryset)

    # -- capability blocks ---------------------------------------------------

    def global_capabilities(self):
        from chaotica_utils.audit import user_is_global_admin

        u = self.user
        return {
            "can_scope": self.has_any_unit_perm("jobtracker.can_scope_jobs"),
            "can_signoff_scopes": self.has_any_unit_perm(
                "jobtracker.can_signoff_scopes"
            ),
            "can_tqa": self.has_any_unit_perm("jobtracker.can_tqa_jobs"),
            "can_pqa": self.has_any_unit_perm("jobtracker.can_pqa_jobs"),
            "can_deliver": self.has_any_unit_perm("jobtracker.can_deliver_job"),
            "can_schedule": self.has_any_unit_perm("jobtracker.can_schedule_job"),
            "can_view_loaded_costs": u.is_superuser
            or u.has_perm("jobtracker.can_view_loaded_costs")
            or self.has_any_unit_perm("jobtracker.can_view_loaded_costs"),
            "is_people_manager": self._memo("pm", u.is_people_manager),
            "is_global_admin": self._memo("ga", lambda: user_is_global_admin(u)),
            "can_manage_users": u.has_perm("chaotica_utils.manage_user"),
        }

    def capabilities(self, obj):
        from .models import Job, Phase

        if isinstance(obj, Job):
            return {
                "can_update": self.can("job.update", obj),
                "can_view_schedule": self.can("job.view_schedule", obj),
                "can_view_loaded_costs": self.can("job.view_loaded_costs", obj),
            }
        if isinstance(obj, Phase):
            return {
                "can_update": self.can("phase.update", obj),
                "can_view_schedule": self.can("job.view_schedule", obj.job),
            }
        return {}


# ---------------------------------------------------------------------------
# Object rules: (policy, obj) -> bool
# ---------------------------------------------------------------------------


def _can_view_job(p, job):
    from .utils import can_view_job

    return can_view_job(p.user, job)


def _can_view_job_schedule(p, job):
    from .utils import can_view_job_schedule

    return can_view_job_schedule(p.user, job)


def _can_view_loaded_costs(p, job):
    u = p.user
    if u.is_superuser:
        return True
    return bool(job.unit_id) and u.has_perm(
        "jobtracker.can_view_loaded_costs", job.unit
    )


def _can_view_user(p, target):
    return p.user.has_perm("chaotica_utils.view_user") or p.user.has_perm(
        "chaotica_utils.view_user", target
    )


_CAN = {
    "job.view": _can_view_job,
    "job.update": lambda p, job: p.job_perm("jobtracker.can_update_job", job),
    "job.view_schedule": _can_view_job_schedule,
    "job.view_loaded_costs": _can_view_loaded_costs,
    "phase.view": lambda p, phase: _can_view_job(p, phase.job),
    "phase.update": lambda p, phase: p.job_perm("jobtracker.can_update_job", phase),
    "user.view": _can_view_user,
}


# ---------------------------------------------------------------------------
# Queryset rules: (policy, queryset) -> queryset
# Moved from the v1 viewsets' scope_queryset; each mirrors its UI list view.
# ---------------------------------------------------------------------------


def _scope_jobs(p, qs):
    # JobPermissionRequiredMixin: unit can_view_jobs OR the job-team bypass.
    # jobs_for_user is distinct and jobs_with_unit_permission isn't, so union
    # pks rather than combining the querysets with |.
    from .models import Job

    ids = set(
        Job.objects.jobs_with_unit_permission(
            p.user, "jobtracker.can_view_jobs"
        ).values_list("pk", flat=True)
    )
    ids.update(Job.objects.jobs_for_user(p.user).values_list("pk", flat=True))
    return qs.filter(pk__in=ids)


def _scope_phases(p, qs):
    from .models import Phase

    ids = set(
        Phase.objects.phases_with_unit_permission(
            p.user, "jobtracker.can_view_jobs"
        ).values_list("pk", flat=True)
    )
    ids.update(Phase.objects.phases_for_user(p.user).values_list("pk", flat=True))
    return qs.filter(pk__in=ids)


def _scope_projects(p, qs):
    # view_project model perm (global or per object, as ProjectListView) plus
    # the team-membership bypass.
    from .models import Project

    ids = set(
        get_objects_for_user(
            p.user, "jobtracker.view_project", klass=Project
        ).values_list("pk", flat=True)
    )
    ids.update(Project.objects.projects_for_user(p.user).values_list("pk", flat=True))
    return qs.filter(pk__in=ids)


def _scope_by_model_perm(perm, klass_path):
    def rule(p, qs):
        from django.apps import apps

        klass = apps.get_model(klass_path)
        allowed = get_objects_for_user(p.user, perm, klass=klass)
        return qs.filter(pk__in=allowed.values_list("pk", flat=True))

    return rule


def _scope_users(p, qs):
    from chaotica_utils.models import User

    allowed = get_objects_for_user(p.user, "chaotica_utils.view_user", klass=User)
    return qs.filter(pk__in=allowed.values_list("pk", flat=True))


def _scope_timeslots(p, qs):
    # Same visibility as the scheduler: view_users_schedule on a unit the
    # person is a current member of (or is deactivated in), plus own slots.
    from .utils import viewable_schedule_user_pks

    return qs.filter(user_id__in=viewable_schedule_user_pks(p.user))


def _scope_leave(p, qs):
    # The manage_leave visibility clause.
    u = p.user
    return qs.filter(
        Q(user__unit_memberships__unit__in=p.units("can_view_all_leave_requests"))
        | Q(user__manager=u)
        | Q(user__acting_manager=u)
        | Q(user=u)
    ).distinct()


def _scope_own_or_managed(global_perm):
    def rule(p, qs):
        u = p.user
        if u.has_perm(global_perm):
            return qs
        return qs.filter(
            Q(user=u) | Q(user__manager=u) | Q(user__acting_manager=u)
        ).distinct()

    return rule


_SCOPE = {
    "job.view": _scope_jobs,
    "phase.view": _scope_phases,
    "project.view": _scope_projects,
    "client.view": _scope_by_model_perm("jobtracker.view_client", "jobtracker.Client"),
    "org_unit.view": _scope_by_model_perm(
        "jobtracker.view_organisationalunit", "jobtracker.OrganisationalUnit"
    ),
    "skill.view": _scope_by_model_perm("jobtracker.view_skill", "jobtracker.Skill"),
    "qualification.view": _scope_by_model_perm(
        "jobtracker.view_qualification", "jobtracker.Qualification"
    ),
    "service.view": _scope_by_model_perm(
        "jobtracker.view_service", "jobtracker.Service"
    ),
    "user.view": _scope_users,
    "timeslot.view": _scope_timeslots,
    "leave.view": _scope_leave,
    "user_skill.view": _scope_own_or_managed("jobtracker.view_users_skill"),
    "qualification_record.view": _scope_own_or_managed(
        "jobtracker.view_users_qualifications"
    ),
}
