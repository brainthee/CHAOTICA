from django.http import HttpResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from chaotica_utils.utils import make_aware, get_start_of_week
from django.utils import timezone
from datetime import datetime, timedelta
from jobtracker.models import Job, Phase, TimeSlot, OrganisationalUnit
from chaotica_utils.models import LeaveRequest, User, UserJobLevel
from jobtracker.enums import JobStatuses, PhaseStatuses
from chaotica_utils.views import page_defaults
from django.db.models import Q, Prefetch
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


@login_required
@require_safe
def index(request):
    context = {}

    # this week's datetime objects
    week_start_date = timezone.now().date() - timedelta(
        days=timezone.now().date().weekday()
    )
    week_end_date = week_start_date + timedelta(days=6)

    # Compute permission-based unit querysets once (avoids duplicate
    # get_objects_for_user calls in both the view and template)
    units_can_view = get_objects_for_user(
        request.user, "can_view_jobs", klass=OrganisationalUnit
    )
    units_can_scope = get_objects_for_user(
        request.user, "can_scope_jobs", klass=OrganisationalUnit
    )
    units_can_signoff = get_objects_for_user(
        request.user, "can_signoff_scopes", klass=OrganisationalUnit
    )
    units_can_tqa = get_objects_for_user(
        request.user, "can_tqa_jobs", klass=OrganisationalUnit
    )
    units_can_pqa = get_objects_for_user(
        request.user, "can_pqa_jobs", klass=OrganisationalUnit
    )
    units_can_deliver = get_objects_for_user(
        request.user, "can_deliver_jobs", klass=OrganisationalUnit
    )
    # Unit managers (change_organisationalunit) get the full unit-wide alarm view;
    # schedulers (can_schedule_job, held by Manager + Service Delivery) get the
    # "phases with no schedule" alarm unit-wide.
    units_can_manage = get_objects_for_user(
        request.user, "change_organisationalunit", klass=OrganisationalUnit
    )
    units_can_schedule = get_objects_for_user(
        request.user, "can_schedule_job", klass=OrganisationalUnit
    )

    # Boolean flags for template tab visibility
    can_scope = units_can_scope.exists()
    can_signoff_scope = units_can_signoff.exists()
    can_tqa = units_can_tqa.exists()
    can_pqa = units_can_pqa.exists()
    can_deliver = units_can_deliver.exists()
    is_people_mgr = request.user.is_people_manager()

    context["can_scope"] = can_scope
    context["can_signoff_scope"] = can_signoff_scope
    context["can_tqa"] = can_tqa
    context["can_pqa"] = can_pqa
    context["can_deliver"] = can_deliver
    context["is_people_manager"] = is_people_mgr

    all_phases = Phase.objects.filter(
        Q(job__unit__in=units_can_view),
        status__in=PhaseStatuses.ACTIVE_STATUSES,  # Include active phase statuses only
        job__status__in=JobStatuses.ACTIVE_STATUSES,  # Include active job statuses only
    )

    has_oversight_role = (
        can_tqa or can_pqa or can_scope or can_signoff_scope or can_deliver
    )

    # In Flight / Scheduled This Week / Upcoming Reports show a unit-wide view for
    # people-managers and oversight roles; everyone else sees only phases they are
    # personally involved in (scheduled / lead / report author).
    if is_people_mgr or has_oversight_role:
        operational_base = all_phases
    else:
        operational_base = Phase.objects.phases_for_user(request.user)

    # Eagerly evaluate querysets with list() so the template can use
    # |length instead of .count (avoids duplicate COUNT queries)
    context["myJobs"] = list(
        Job.objects.jobs_for_user(request.user).select_related(
            "client", "unit"
        ).prefetch_related("phases")
    )
    context["myPhases"] = list(
        Phase.objects.phases_for_user(request.user).select_related(
            "service", "job__client", "project_lead", "report_author"
        )
    )

    context["in_flight"] = list(
        operational_base.filter(
            Q(status=PhaseStatuses.IN_PROGRESS)
        ).select_related(
            "service",
            "job__client",
            "project_lead",
            "report_author",
        )
    )

    if can_tqa:
        context["TQA"] = list(
            all_phases.filter(
                Q(status=PhaseStatuses.PENDING_TQA)
                | Q(status=PhaseStatuses.QA_TECH)
                | Q(status=PhaseStatuses.QA_TECH_AUTHOR_UPDATES)
            )
            .exclude(
                Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0)
            )
            .annotate(
                db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
            )
            .order_by("db_delivery_date")
            .select_related(
                "service",
                "job__client",
                "project_lead",
                "report_author",
                "techqa_by",
            )
        )
    else:
        context["TQA"] = []

    if can_pqa:
        context["PQA"] = list(
            all_phases.filter(
                Q(status=PhaseStatuses.PENDING_PQA)
                | Q(status=PhaseStatuses.QA_PRES)
                | Q(status=PhaseStatuses.QA_PRES_AUTHOR_UPDATES)
            )
            .exclude(
                Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0)
            )
            .annotate(
                db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
            )
            .order_by("db_delivery_date")
            .select_related(
                "service",
                "job__client",
                "project_lead",
                "report_author",
                "presqa_by",
            )
        )
    else:
        context["PQA"] = []

    twoweeks = get_start_of_week() + timedelta(weeks=2)
    context["upcoming_reports_date"] = twoweeks
    context["upcoming_reports"] = list(
        operational_base.annotate(
            db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
        )
        .filter(Q(status__lt=PhaseStatuses.DELIVERED) & Q(db_delivery_date__lte=twoweeks))
        .exclude(
            Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0)
        )
        .order_by("db_delivery_date")
        .select_related(
            "service",
            "job__client",
            "project_lead",
            "report_author",
            "presqa_by",
        )
    )

    context["scheduled_phases_this_week"] = list(
        operational_base.filter(
            timeslots__end__date__gte=week_start_date,
            timeslots__start__date__lte=week_end_date,
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

    if can_scope:
        context["pendingScoping"] = list(
            Job.objects.filter(
                Q(unit__in=units_can_scope),
                Q(status=JobStatuses.PENDING_SCOPE)
                | Q(status=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
                | Q(status=JobStatuses.SCOPING),
            ).select_related("unit", "client")
            .prefetch_related("phases", "scoped_by")
        )
    else:
        context["pendingScoping"] = []

    if can_signoff_scope:
        context["scopesToSignoff"] = list(
            Job.objects.filter(
                Q(unit__in=units_can_signoff),
                status=JobStatuses.PENDING_SCOPING_SIGNOFF,
            ).select_related("unit", "client")
            .prefetch_related("phases")
        )
    else:
        context["scopesToSignoff"] = []

    if is_people_mgr:
        current_levels_prefetch = Prefetch(
            'job_level_history',
            queryset=UserJobLevel.objects.filter(is_current=True),
            to_attr='_current_levels',
        )
        context["team"] = User.objects.filter(
            Q(manager=request.user) | Q(acting_manager=request.user),
            is_active=True,
        ).select_related(
            'city__country',
        ).prefetch_related(
            'unit_memberships__unit',
            current_levels_prefetch,
            'qualifications__qualification__awarding_body',
            'skills__skill__category',
        )
        context["team_leave"] = LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        ).select_related(
            'user__city__country',
        ).prefetch_related(
            'user__unit_memberships__unit',
            Prefetch(
                'user__job_level_history',
                queryset=UserJobLevel.objects.filter(is_current=True),
                to_attr='_current_levels',
            ),
        )

    if can_deliver:
        context["pendingDelivery"] = list(
            Phase.objects.filter(
                Q(job__unit__in=units_can_deliver),
                Q(status=PhaseStatuses.COMPLETED)
            ).select_related(
                "project_lead", "job__client", "job__account_manager",
            ).prefetch_related("job__unit")
        )
    else:
        context["pendingDelivery"] = []

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

    # --- Alarms ---
    today = timezone.now().date()

    # Alarm visibility is scoped per-role and per-category:
    #   * "On the team" (scheduled on / lead / report author of a phase) -> every
    #     alarm for that phase/job, regardless of the warning type.
    #   * Unit managers (change_organisationalunit) -> all alarms unit-wide.
    #   * TQA role -> TQA alarms unit-wide; PQA role -> PQA alarms unit-wide.
    #   * Schedulers / Service Delivery (can_schedule_job) -> unscheduled unit-wide.
    # A plain scoper/consultant with none of these only sees their own team's alarms.
    manager_units = (
        units_can_view
        if units_can_manage.exists()
        else OrganisationalUnit.objects.none()
    )

    phase_involved = (
        Q(timeslots__user=request.user)
        | Q(report_author=request.user)
        | Q(project_lead=request.user)
    )
    job_involved = (
        Q(phases__timeslots__user=request.user)
        | Q(phases__report_author=request.user)
        | Q(phases__project_lead=request.user)
        | Q(scoped_by=request.user)
        | Q(account_manager=request.user)
        | Q(dep_account_manager=request.user)
    )

    def _alarm_phases(unit_scope):
        # Active phases the user is on the team of, plus active phases in the
        # given role-scoped units.
        return Phase.objects.filter(
            Q(job__unit__in=unit_scope) | phase_involved,
            status__in=PhaseStatuses.ACTIVE_STATUSES,
            job__status__in=JobStatuses.ACTIVE_STATUSES,
        ).distinct()

    base_mgr = _alarm_phases(manager_units)
    base_tqa = _alarm_phases(manager_units | units_can_tqa)
    base_pqa = _alarm_phases(manager_units | units_can_pqa)
    base_sched = _alarm_phases(manager_units | units_can_schedule)
    alarm_job_qs = Job.objects.filter(
        Q(unit__in=manager_units) | job_involved,
        status__in=JobStatuses.ACTIVE_STATUSES,
    ).distinct()

    alarms = {}

    alarms["delivery_overdue"] = list(
        base_mgr.annotate(
            db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
        ).filter(db_delivery_date__lt=today).select_related(
            "service", "job__client", "project_lead", "report_author"
        )
    )

    alarms["tqa_overdue"] = list(
        base_tqa.annotate(
            db_tqa_date=Coalesce("due_to_techqa_set", "_due_to_techqa")
        ).filter(
            db_tqa_date__lt=today,
            status__in=[
                PhaseStatuses.IN_PROGRESS, PhaseStatuses.PENDING_TQA,
                PhaseStatuses.QA_TECH, PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
            ],
        ).select_related("service", "job__client", "project_lead", "report_author", "techqa_by")
    )

    alarms["pqa_overdue"] = list(
        base_pqa.annotate(
            db_pqa_date=Coalesce("due_to_presqa_set", "_due_to_presqa")
        ).filter(
            db_pqa_date__lt=today,
            status__in=[
                PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES,
                PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
            ],
        ).select_related("service", "job__client", "project_lead", "report_author", "presqa_by")
    )

    alarms["no_techqa"] = list(
        base_tqa.filter(
            techqa_by__isnull=True,
            status__in=[
                PhaseStatuses.PENDING_TQA, PhaseStatuses.QA_TECH,
                PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
            ],
        ).select_related("service", "job__client", "project_lead", "report_author")
    )

    alarms["no_presqa"] = list(
        base_pqa.filter(
            presqa_by__isnull=True,
            status__in=[
                PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES,
                PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
            ],
        ).select_related("service", "job__client", "project_lead", "report_author")
    )

    alarms["unscheduled"] = list(
        base_sched.filter(
            status__in=[
                PhaseStatuses.SCHEDULED_TENTATIVE, PhaseStatuses.SCHEDULED_CONFIRMED,
                PhaseStatuses.PRE_CHECKS, PhaseStatuses.CLIENT_NOT_READY,
                PhaseStatuses.READY_TO_BEGIN, PhaseStatuses.IN_PROGRESS,
            ],
        ).filter(timeslots__isnull=True).select_related("service", "job__client", "project_lead")
    )

    alarms["job_overdue"] = list(
        alarm_job_qs.annotate(
            db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
        ).filter(db_delivery_date__lt=today).select_related("client", "unit")
    )

    context["alarms"] = alarms
    context["alarm_count"] = sum(len(v) for v in alarms.values())
    # Show alarms tab by default only when there are alarms to display.
    context["show_alarms_first"] = context["alarm_count"] > 0

    context = {**context, **page_defaults(request)}
    template = loader.get_template("dashboard_index.html")
    return HttpResponse(template.render(context, request))
