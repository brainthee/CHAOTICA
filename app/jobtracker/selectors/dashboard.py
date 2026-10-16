"""Dashboard queues: which tabs a user gets and what is in each.

Shared by the dashboard page (``dashboard/views.py``) and the API
(``/api/v1/me/dashboard/``, ``?queue=`` on jobs and phases).
"""

from datetime import timedelta

from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.functional import cached_property

from chaotica_utils.utils import get_start_of_week

from ..enums import JobStatuses, PhaseStatuses
from ..models import Job, OrganisationalUnit, Phase
from ..policy import PolicyContext
from .involvement import job_involvement_q, phase_involvement_q


class DashboardScope:
    """Per-request permission scoping shared by the dashboard index (tab list
    and badge counts) and each tab's partial view, so both always agree.

    Everything is lazy: a tab partial only pays for the scoping it uses."""

    def __init__(self, user, policy=None, today=None):
        self.user = user
        self.policy = policy or PolicyContext(user)
        self.today = today or timezone.now().date()

    def _units(self, perm):
        return self.policy.units(perm)

    @cached_property
    def member_units(self):
        # Queue tabs are scoped to the units the user is actually a MEMBER of
        # (intersected with the relevant permission) — NOT every unit a global
        # role happens to grant can_view/can_tqa/etc. across. The personal-
        # involvement predicates are OR'd in so work the user is directly
        # assigned to (e.g. doing PQA on a phase in another unit) still shows
        # regardless of membership. Alarms keep their own wider role scoping.
        return OrganisationalUnit.objects.filter(
            members__member=self.user, members__left_date__isnull=True
        )

    def _member(self, perm):
        return self._units(perm).filter(pk__in=self.member_units)

    @cached_property
    def can_scope(self):
        return self._units("can_scope_jobs").exists()

    @cached_property
    def can_signoff_scope(self):
        return self._units("can_signoff_scopes").exists()

    @cached_property
    def can_tqa(self):
        return self._units("can_tqa_jobs").exists()

    @cached_property
    def can_pqa(self):
        return self._units("can_pqa_jobs").exists()

    @cached_property
    def can_deliver(self):
        return self._units("can_deliver_job").exists()

    @cached_property
    def is_people_manager(self):
        return self.user.is_people_manager()

    @cached_property
    def phase_involved(self):
        return phase_involvement_q(self.user)

    @cached_property
    def job_involved(self):
        return job_involvement_q(self.user)

    @cached_property
    def all_phases(self):
        return Phase.objects.filter(
            Q(job__unit__in=self._member("can_view_jobs")) | self.phase_involved,
            status__in=PhaseStatuses.ACTIVE_STATUSES,  # active phase statuses only
            job__status__in=JobStatuses.ACTIVE_STATUSES,  # active job statuses only
        ).distinct()

    @cached_property
    def operational_base(self):
        # In Flight / Scheduled This Week / Upcoming Reports show a unit-wide
        # view for people-managers and oversight roles; everyone else sees only
        # phases they are personally involved in (scheduled / lead / author).
        oversight = (
            self.can_tqa
            or self.can_pqa
            or self.can_scope
            or self.can_signoff_scope
            or self.can_deliver
        )
        if self.is_people_manager or oversight:
            return self.all_phases
        return Phase.objects.phases_for_user(self.user)

    # --- tab querysets (unevaluated: index counts them, partials list them) ---

    def my_jobs(self):
        return (
            Job.objects.jobs_for_user(self.user)
            .select_related("client", "unit")
            .prefetch_related("phases")
        )

    def my_phases(self):
        return Phase.objects.phases_for_user(self.user).select_related(
            "service", "job__client", "project_lead", "report_author"
        )

    def in_flight(self):
        return self.operational_base.filter(
            status=PhaseStatuses.IN_PROGRESS
        ).select_related("service", "job__client", "project_lead", "report_author")

    def scheduled_this_week(self):
        week_start = self.today - timedelta(days=self.today.weekday())
        week_end = week_start + timedelta(days=6)
        return (
            self.operational_base.filter(
                timeslots__end__date__gte=week_start,
                timeslots__start__date__lte=week_end,
            )
            .distinct()
            .select_related(
                "service",
                "project_lead",
                "report_author",
                "techqa_by",
                "presqa_by",
                "job__client",
            )
            .prefetch_related("timeslots")
        )

    @staticmethod
    def upcoming_reports_date():
        return get_start_of_week() + timedelta(weeks=2)

    def upcoming_reports(self):
        return (
            self.operational_base.annotate(
                db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
            )
            .filter(
                Q(status__lt=PhaseStatuses.DELIVERED)
                & Q(db_delivery_date__lte=self.upcoming_reports_date())
            )
            .exclude(Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0))
            .order_by("db_delivery_date")
            .select_related(
                "service",
                "job__client",
                "project_lead",
                "report_author",
                "presqa_by",
            )
        )

    def scoping(self):
        return (
            Job.objects.filter(
                Q(unit__in=self._member("can_scope_jobs")) | self.job_involved,
                Q(status=JobStatuses.PENDING_SCOPE)
                | Q(status=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
                | Q(status=JobStatuses.SCOPING),
            )
            .distinct()
            .select_related("unit", "client")
            .prefetch_related("phases", "scoped_by")
        )

    def signoff(self):
        return (
            Job.objects.filter(
                Q(unit__in=self._member("can_signoff_scopes")) | self.job_involved,
                status=JobStatuses.PENDING_SCOPING_SIGNOFF,
            )
            .distinct()
            .select_related("unit", "client")
            .prefetch_related("phases")
        )

    def _qa(self, statuses, reviewer):
        return (
            self.all_phases.filter(status__in=statuses)
            .exclude(Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0))
            .annotate(
                db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
            )
            .order_by("db_delivery_date")
            .select_related(
                "service",
                "job__client",
                "project_lead",
                "report_author",
                reviewer,
            )
        )

    def tqa(self):
        return self._qa(
            [
                PhaseStatuses.PENDING_TQA,
                PhaseStatuses.QA_TECH,
                PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
            ],
            "techqa_by",
        )

    def pqa(self):
        return self._qa(
            [
                PhaseStatuses.PENDING_PQA,
                PhaseStatuses.QA_PRES,
                PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
            ],
            "presqa_by",
        )

    def pending_delivery(self):
        return (
            Phase.objects.filter(
                Q(job__unit__in=self._member("can_deliver_job")) | self.phase_involved,
                status=PhaseStatuses.COMPLETED,
                job__status__in=JobStatuses.ACTIVE_STATUSES,  # not deleted/archived/lost
            )
            .distinct()
            .select_related(
                "project_lead",
                "job__client",
                "job__account_manager",
                "job__unit",
            )
        )

    # --- alarms (scoping + rules live in jobtracker.alarms) ---

    @cached_property
    def alarm_querysets(self):
        from jobtracker.alarms import build_alarms

        return build_alarms(self.user, self.policy)

    def alarm_context(self):
        """Materialised alarm lists + counts for ``partials/alarms_table.html``."""
        from jobtracker.alarms import STALE_KEYS

        phase_related = ("service", "job__client", "project_lead", "report_author")
        alarms = {}
        for key, qs in self.alarm_querysets.items():
            if qs.model is Job:
                alarms[key] = list(
                    qs.select_related("client", "unit", "account_manager")
                )
            else:
                related = phase_related
                if key == "tqa_overdue":
                    related += ("techqa_by",)
                elif key == "pqa_overdue":
                    related += ("presqa_by",)
                alarms[key] = list(qs.select_related(*related))
        # The red tab badge counts overdue work only; stale items are listed
        # (and badged) separately so old leftovers don't drown out what's late.
        stale = sum(len(alarms[k]) for k in STALE_KEYS)
        return {
            "alarms": alarms,
            "stale_alarm_count": stale,
            "alarm_count": sum(len(v) for v in alarms.values()) - stale,
        }


#: Lazy dashboard tabs: key -> (queryset method, audience flag, template).
#: ``None`` audience = everyone. Alarms are handled separately.
DASHBOARD_TABS = {
    "my_jobs": ("my_jobs", None, "partials/tabs/job_table.html"),
    "my_phases": ("my_phases", None, "partials/tabs/phase_table.html"),
    "in_flight": ("in_flight", None, "partials/tabs/phase_table.html"),
    "scheduled_this_week": (
        "scheduled_this_week",
        None,
        "partials/tabs/phase_table.html",
    ),
    "upcoming_reports": ("upcoming_reports", None, "partials/tabs/phase_table.html"),
    "scoping": ("scoping", "can_scope", "partials/tabs/scoping_table.html"),
    "signoff": ("signoff", "can_signoff_scope", "partials/tabs/scoping_table.html"),
    "tqa": ("tqa", "can_tqa", "partials/tabs/tqa_table.html"),
    "pqa": ("pqa", "can_pqa", "partials/tabs/pqa_table.html"),
    "pending_delivery": (
        "pending_delivery",
        "can_deliver",
        "partials/tabs/delivery_table.html",
    ),
}


#: Queue key -> (label, list resource the key filters with ``?queue=``).
QUEUE_META = {
    "my_jobs": ("My Jobs", "jobs"),
    "my_phases": ("My Phases", "phases"),
    "in_flight": ("In Flight", "phases"),
    "scheduled_this_week": ("Scheduled This Week", "phases"),
    "upcoming_reports": ("Upcoming Reports", "phases"),
    "scoping": ("Scoping", "jobs"),
    "signoff": ("Pending Signoff", "jobs"),
    "tqa": ("Technical QA", "phases"),
    "pqa": ("Presentation QA", "phases"),
    "pending_delivery": ("Pending Delivery", "phases"),
}


def visible_queue_keys(scope):
    return [
        key
        for key, (_method, audience, _tmpl) in DASHBOARD_TABS.items()
        if audience is None or getattr(scope, audience)
    ]


def queue_queryset(scope, key):
    """The queryset behind dashboard queue ``key``. Raises ``KeyError`` for an
    unknown key and ``PermissionError`` when the user doesn't get that tab."""
    method, audience, _tmpl = DASHBOARD_TABS[key]
    if audience is not None and not getattr(scope, audience):
        raise PermissionError(key)
    return getattr(scope, method)()


def dashboard_queues(scope):
    """``[{key, label, count, resource}]`` for the tabs this user gets."""
    out = []
    for key in visible_queue_keys(scope):
        label, resource = QUEUE_META[key]
        out.append(
            {
                "key": key,
                "label": label,
                "count": queue_queryset(scope, key).count(),
                "resource": resource,
            }
        )
    return out


def consultant_stats(user):
    return {
        "jobs_participated": user.get_jobs().count(),
        "jobs_led": user.phase_where_project_lead.count(),
        "reports_authored": user.phase_where_report_author.count(),
        "scoped": user.engagements_that_scoped.count(),
        "qaed": user.techqaed_phases.count(),
    }


def qa_feedback(user):
    return {
        "avg_tqa_rating": user.get_average_techqa_feedback(),
        "avg_pqa_rating": user.get_average_presqa_feedback(),
        "tqa_feedback_12mo": user.get_average_techqa_feedback_12mo(),
        "pqa_feedback_12mo": user.get_average_presqa_feedback_12mo(),
    }


def team_members(manager):
    """Active direct (and acting) reports, with what the team cards render."""
    from chaotica_utils.models import User, UserJobLevel
    from django.db.models import Prefetch

    return (
        User.objects.filter(
            Q(manager=manager) | Q(acting_manager=manager), is_active=True
        )
        .select_related("city__country")
        .prefetch_related(
            "unit_memberships__unit",
            Prefetch(
                "job_level_history",
                queryset=UserJobLevel.objects.filter(is_current=True),
                to_attr="_current_levels",
            ),
            "qualifications__qualification__awarding_body",
            "skills__skill__category",
        )
    )


def team_leave_requests(manager):
    """Leave requests from the manager's reports, flagged where they overlap
    booked delivery work (``overlaps_work_ann``)."""
    from chaotica_utils.models import LeaveRequest, UserJobLevel
    from django.db.models import Exists, OuterRef, Prefetch

    from ..enums import DefaultTimeSlotTypes
    from ..models import TimeSlot

    overlap = TimeSlot.objects.filter(
        user=OuterRef("user"),
        slot_type=DefaultTimeSlotTypes.DELIVERY,
        start__lte=OuterRef("end_date"),
        end__gte=OuterRef("start_date"),
    )
    return (
        LeaveRequest.objects.filter(
            Q(user__manager=manager) | Q(user__acting_manager=manager)
        )
        .select_related("user__city__country", "user__manager", "user__acting_manager")
        .prefetch_related(
            "user__unit_memberships__unit",
            Prefetch(
                "user__job_level_history",
                queryset=UserJobLevel.objects.filter(is_current=True),
                to_attr="_current_levels",
            ),
        )
        .annotate(overlaps_work_ann=Exists(overlap))
    )


# --- alarms ---------------------------------------------------------------

#: Which date and people an alarm row is about, per key.
_ALARM_DATE = {
    "delivery_overdue": "delivery_date",
    "tqa_overdue": "due_to_techqa",
    "pqa_overdue": "due_to_presqa",
    "job_overdue": "delivery_date",
}
_ALARM_PEOPLE = {
    "tqa_overdue": ("techqa_by",),
    "pqa_overdue": ("presqa_by",),
}


def _value(obj, attr):
    value = getattr(obj, attr, None)
    return value() if callable(value) else value


def alarm_groups(scope):
    """``{"overdue": [group], "stale": [group], "counts": {...}}`` where a group
    is ``{key, label, severity, items[{obj, date, people, message}]}``."""
    from ..alarms import ALARM_LABELS, STALE_KEYS

    ctx = scope.alarm_context()
    overdue, stale = [], []
    for key, objs in ctx["alarms"].items():
        if not objs:
            continue
        label = ALARM_LABELS.get(key, key)
        items = []
        for obj in objs:
            if isinstance(obj, Job):
                people = [obj.account_manager]
                date = obj.delivery_date()
            else:
                people = [obj.project_lead, obj.report_author] + [
                    getattr(obj, a) for a in _ALARM_PEOPLE.get(key, ())
                ]
                date = _value(obj, _ALARM_DATE.get(key, "delivery_date"))
            message = f"{label}: due {date:%d %b %Y}" if date else label
            items.append(
                {
                    "obj": obj,
                    "date": date,
                    "people": [p for p in people if p is not None],
                    "message": message,
                }
            )
        group = {
            "key": key,
            "label": label,
            "severity": (
                "warning"
                if key in STALE_KEYS or key.startswith("no_") or key == "unscheduled"
                else "critical"
            ),
            "items": items,
        }
        (stale if key in STALE_KEYS else overdue).append(group)
    return {
        "overdue": overdue,
        "stale": stale,
        "counts": {
            "overdue": ctx["alarm_count"],
            "stale": ctx["stale_alarm_count"],
            "total": ctx["alarm_count"] + ctx["stale_alarm_count"],
        },
    }


# --- stats ----------------------------------------------------------------


def _window(today, days, offset=0):
    from datetime import datetime, time

    end = today - timedelta(days=offset)
    start = end - timedelta(days=days - 1)
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start, time.min), tz),
        timezone.make_aware(datetime.combine(end, time.max), tz),
    )


def _utilisation(users, today, days=30, offset=0):
    """``{user_id: utilisation %}`` over ``days`` ending ``offset`` days ago."""
    from chaotica_utils.models import User

    start, end = _window(today, days, offset)
    by_user = User.objects.calculate_bulk_utilization(users, start, end)["by_user"]
    return {uid: data.get("utilisation_percentage") for uid, data in by_user.items()}


def user_stats(user):
    return {"consultant": consultant_stats(user), **qa_feedback(user)}


def dashboard_stats(user, today):
    from chaotica_utils.models import LeaveRequest, User

    me = User.objects.filter(pk=user.pk)
    return {
        **user_stats(user),
        "utilisation_30d": _utilisation(me, today).get(user.pk),
        "utilisation_prior_30d": _utilisation(me, today, offset=30).get(user.pk),
        # No utilisation target is configured anywhere yet.
        "utilisation_target": None,
        "leave_remaining_days": float(user.remaining_leave()),
        "leave_pending_requests": LeaveRequest.objects.filter(
            user=user, authorised=False, declined=False, cancelled=False
        ).count(),
    }


def primary_unit(user):
    """The user's first current unit (by when they joined it)."""
    membership = (
        user.unit_memberships.filter(left_date__isnull=True)
        .select_related("unit")
        .order_by("pk")
        .first()
    )
    return membership.unit if membership else None


def team_utilisation(user, today):
    """``(unit, [{user, utilisation}])`` for the user's primary unit over the
    last 30 days, highest first."""
    from chaotica_utils.models import User

    unit = primary_unit(user)
    if unit is None:
        return None, []
    members = User.objects.filter(
        unit_memberships__unit=unit,
        unit_memberships__left_date__isnull=True,
        is_active=True,
    ).distinct()
    util = _utilisation(members, today)
    rows = [{"user": u, "utilisation": util.get(u.pk)} for u in members]
    rows.sort(key=lambda r: (r["utilisation"] is None, -(r["utilisation"] or 0)))
    return unit, rows
