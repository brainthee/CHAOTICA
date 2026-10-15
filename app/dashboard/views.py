from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, Http404
from django.utils.functional import cached_property
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from chaotica_utils.utils import get_start_of_week
from django.utils import timezone
from datetime import timedelta
from jobtracker.models import Job, Phase, TimeSlot, OrganisationalUnit
from chaotica_utils.models import LeaveRequest, User, UserJobLevel
from jobtracker.enums import JobStatuses, PhaseStatuses, DefaultTimeSlotTypes
from chaotica_utils.views import page_defaults
from django.db.models import Q, Prefetch, Exists, OuterRef
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_safe
from guardian.shortcuts import get_objects_for_user

logger = logging.getLogger(__name__)

# Pending scheduling
# Pending TQA
# Pending PQA
# Upcoming Phases
# List of inflight jobs
# Late Jobs
# This Week's jobs (schedule based)
# AM View?
# People Lead


#: How often the dashboard re-fetches the visible tab (milliseconds).
DASHBOARD_REFRESH_MS = 3 * 60 * 1000


class DashboardScope:
    """Per-request permission scoping shared by the dashboard index (tab list
    and badge counts) and each tab's partial view, so both always agree.

    Everything is lazy: a tab partial only pays for the scoping it uses."""

    def __init__(self, user):
        self.user = user
        self._unit_cache = {}

    def _units(self, perm):
        if perm not in self._unit_cache:
            self._unit_cache[perm] = get_objects_for_user(
                self.user, perm, klass=OrganisationalUnit
            )
        return self._unit_cache[perm]

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
        u = self.user
        return (
            Q(timeslots__user=u)
            | Q(report_author=u)
            | Q(project_lead=u)
            | Q(techqa_by=u)
            | Q(presqa_by=u)
        )

    @cached_property
    def job_involved(self):
        u = self.user
        return (
            Q(phases__timeslots__user=u)
            | Q(phases__report_author=u)
            | Q(phases__project_lead=u)
            | Q(phases__techqa_by=u)
            | Q(phases__presqa_by=u)
            | Q(scoped_by=u)
            | Q(account_manager=u)
            | Q(dep_account_manager=u)
        )

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
            self.can_tqa or self.can_pqa or self.can_scope
            or self.can_signoff_scope or self.can_deliver
        )
        if self.is_people_manager or oversight:
            return self.all_phases
        return Phase.objects.phases_for_user(self.user)

    # --- tab querysets (unevaluated: index counts them, partials list them) ---

    def my_jobs(self):
        return Job.objects.jobs_for_user(self.user).select_related(
            "client", "unit"
        ).prefetch_related("phases")

    def my_phases(self):
        return Phase.objects.phases_for_user(self.user).select_related(
            "service", "job__client", "project_lead", "report_author"
        )

    def in_flight(self):
        return self.operational_base.filter(
            status=PhaseStatuses.IN_PROGRESS
        ).select_related("service", "job__client", "project_lead", "report_author")

    def scheduled_this_week(self):
        week_start = timezone.now().date() - timedelta(days=timezone.now().date().weekday())
        week_end = week_start + timedelta(days=6)
        return (
            self.operational_base.filter(
                timeslots__end__date__gte=week_start,
                timeslots__start__date__lte=week_end,
            )
            .distinct()
            .select_related(
                "service", "project_lead", "report_author", "techqa_by",
                "presqa_by", "job__client",
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
                "service", "job__client", "project_lead", "report_author", "presqa_by",
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
            .annotate(db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date"))
            .order_by("db_delivery_date")
            .select_related(
                "service", "job__client", "project_lead", "report_author", reviewer,
            )
        )

    def tqa(self):
        return self._qa(
            [PhaseStatuses.PENDING_TQA, PhaseStatuses.QA_TECH,
             PhaseStatuses.QA_TECH_AUTHOR_UPDATES],
            "techqa_by",
        )

    def pqa(self):
        return self._qa(
            [PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES,
             PhaseStatuses.QA_PRES_AUTHOR_UPDATES],
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
                "project_lead", "job__client", "job__account_manager", "job__unit",
            )
        )

    # --- alarms (scoping + rules live in jobtracker.alarms) ---

    @cached_property
    def alarm_querysets(self):
        from jobtracker.alarms import build_alarms

        return build_alarms(self.user)

    def alarm_context(self):
        """Materialised alarm lists + counts for ``partials/alarms_table.html``."""
        from jobtracker.alarms import STALE_KEYS

        phase_related = ("service", "job__client", "project_lead", "report_author")
        alarms = {}
        for key, qs in self.alarm_querysets.items():
            if qs.model is Job:
                alarms[key] = list(qs.select_related("client", "unit", "account_manager"))
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
    "scheduled_this_week": ("scheduled_this_week", None, "partials/tabs/phase_table.html"),
    "upcoming_reports": ("upcoming_reports", None, "partials/tabs/phase_table.html"),
    "scoping": ("scoping", "can_scope", "partials/tabs/scoping_table.html"),
    "signoff": ("signoff", "can_signoff_scope", "partials/tabs/scoping_table.html"),
    "tqa": ("tqa", "can_tqa", "partials/tabs/tqa_table.html"),
    "pqa": ("pqa", "can_pqa", "partials/tabs/pqa_table.html"),
    "pending_delivery": ("pending_delivery", "can_deliver", "partials/tabs/delivery_table.html"),
}


@login_required
@require_safe
def index(request):
    """First paint only: which tabs exist, their badge counts (COUNT queries),
    which opens first, and the consultant stats. Tab contents load on demand
    (``dashboard_tab``) and refresh themselves while visible."""
    scope = DashboardScope(request.user)
    context = {
        "can_scope": scope.can_scope,
        "can_signoff_scope": scope.can_signoff_scope,
        "can_tqa": scope.can_tqa,
        "can_pqa": scope.can_pqa,
        "can_deliver": scope.can_deliver,
        "is_people_manager": scope.is_people_manager,
        "upcoming_reports_date": scope.upcoming_reports_date(),
        "refresh_ms": DASHBOARD_REFRESH_MS,
    }
    counts = {}
    for key, (method, audience, _tmpl) in DASHBOARD_TABS.items():
        if audience is None or getattr(scope, audience):
            counts[key] = getattr(scope, method)().count()
    context["tab_counts"] = counts

    # Alarms open first when there's overdue work. Most users with alarms
    # have them, so fetch the lists once and render the visible tab inline
    # (no second request); the lists double as the badge counts.
    alarm_ctx = scope.alarm_context()
    context["alarm_count"] = alarm_ctx["alarm_count"]
    context["stale_alarm_count"] = alarm_ctx["stale_alarm_count"]
    context["show_alarms_first"] = alarm_ctx["alarm_count"] > 0
    if context["show_alarms_first"]:
        context["alarms_html"] = loader.render_to_string(
            "partials/alarms_table.html", alarm_ctx, request=request
        )

    # NB: "My Team" / "Team Leave Requests" have their own lazy views
    # (team_tab / team_leave_tab) - the two heaviest panels.

    # Pre-compute consultant stats so the template doesn't hit the DB
    context["consultant_stats"] = {
        "jobs_participated": request.user.get_jobs().count(),
        "jobs_led": request.user.phase_where_project_lead.count(),
        "reports_authored": request.user.phase_where_report_author.count(),
        "scoped": request.user.engagements_that_scoped.count(),
        "qaed": request.user.techqaed_phases.count(),
    }

    # Pre-compute feedback data (avoids 26+ queries from 12-month loops)
    context["avg_tqa_rating"] = request.user.get_average_techqa_feedback()
    context["avg_pqa_rating"] = request.user.get_average_presqa_feedback()
    context["tqa_feedback_12mo"] = request.user.get_average_techqa_feedback_12mo()
    context["pqa_feedback_12mo"] = request.user.get_average_presqa_feedback_12mo()

    context = {**context, **page_defaults(request)}
    template = loader.get_template("dashboard_index.html")
    return HttpResponse(template.render(context, request))


@login_required
@require_safe
def dashboard_tab(request, key):
    """One dashboard tab's content, for lazy load and auto-refresh:
    ``{"html": ..., "count": N}`` (alarms add ``stale``)."""
    scope = DashboardScope(request.user)
    if key == "alarms":
        ctx = scope.alarm_context()
        html = loader.render_to_string("partials/alarms_table.html", ctx, request=request)
        return JsonResponse(
            {"html": html, "count": ctx["alarm_count"], "stale": ctx["stale_alarm_count"]}
        )
    if key not in DASHBOARD_TABS:
        raise Http404()
    method, audience, template = DASHBOARD_TABS[key]
    if audience is not None and not getattr(scope, audience):
        return HttpResponseForbidden()
    items = list(getattr(scope, method)())
    html = loader.render_to_string(
        template,
        {"items": items, "tab_key": key},
        request=request,
    )
    return JsonResponse({"html": html, "count": len(items)})


@login_required
@require_safe
def team_tab(request):
    """Lazy-loaded content for the dashboard "My Team" tab.

    Rendered on demand (first tab-show) rather than as part of index() so the
    initial dashboard load doesn't build a large card per direct report.
    """
    if not request.user.is_people_manager():
        return HttpResponseForbidden()

    current_levels_prefetch = Prefetch(
        "job_level_history",
        queryset=UserJobLevel.objects.filter(is_current=True),
        to_attr="_current_levels",
    )
    team = (
        User.objects.filter(
            Q(manager=request.user) | Q(acting_manager=request.user),
            is_active=True,
        )
        .select_related("city__country")
        .prefetch_related(
            "unit_memberships__unit",
            current_levels_prefetch,
            "qualifications__qualification__awarding_body",
            "skills__skill__category",
        )
    )
    template = loader.get_template("partials/team_dashboard.html")
    return HttpResponse(template.render({"team": team}, request))


@login_required
@require_safe
def team_leave_tab(request):
    """Lazy-loaded content for the dashboard "Team Leave Requests" tab.

    The overlap-with-scheduled-work badge is resolved with an Exists() subquery
    annotation (overlaps_work_ann) instead of a per-row .exists() call.
    """
    if not request.user.is_people_manager():
        return HttpResponseForbidden()

    overlap_subq = TimeSlot.objects.filter(
        user=OuterRef("user"),
        slot_type=DefaultTimeSlotTypes.DELIVERY,
        start__lte=OuterRef("end_date"),
        end__gte=OuterRef("start_date"),
    )
    team_leave = (
        LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        )
        .select_related("user__city__country")
        .prefetch_related(
            "user__unit_memberships__unit",
            Prefetch(
                "user__job_level_history",
                queryset=UserJobLevel.objects.filter(is_current=True),
                to_attr="_current_levels",
            ),
        )
        .annotate(overlaps_work_ann=Exists(overlap_subq))
    )
    template = loader.get_template("partials/team_leave_table.html")
    return HttpResponse(template.render({"team_leave": team_leave}, request))
