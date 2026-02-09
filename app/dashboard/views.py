from django.http import HttpResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from chaotica_utils.utils import make_aware, get_start_of_week
from django.utils import timezone
from datetime import datetime, timedelta
from jobtracker.models import Job, Phase, TimeSlot, OrganisationalUnit
from chaotica_utils.models import LeaveRequest, User
from jobtracker.enums import JobStatuses, PhaseStatuses
from chaotica_utils.views import page_defaults
from django.db.models import Q
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

    # Eagerly evaluate querysets with list() so the template can use
    # |length instead of .count (avoids duplicate COUNT queries)
    context["myJobs"] = list(
        Job.objects.jobs_for_user(request.user).prefetch_related(
            "client", "unit", "phases"
        )
    )
    context["myPhases"] = list(
        Phase.objects.phases_for_user(request.user).prefetch_related(
            "service", "job__client", "project_lead", "report_author"
        )
    )

    context["in_flight"] = list(
        all_phases.filter(
            Q(status=PhaseStatuses.IN_PROGRESS)
        ).prefetch_related(
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
            .prefetch_related(
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
            .prefetch_related(
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
        all_phases.annotate(
            db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
        )
        .filter(Q(status__lt=PhaseStatuses.DELIVERED) & Q(db_delivery_date__lte=twoweeks))
        .exclude(
            Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0)
        )
        .prefetch_related(
            "service",
            "job__client",
            "project_lead",
            "report_author",
            "presqa_by",
        )
    )

    context["scheduled_phases_this_week"] = list(
        all_phases.filter(
            timeslots__end__date__gte=week_start_date,
            timeslots__start__date__lte=week_end_date,
        )
        .distinct()
        .prefetch_related(
            "service",
            "project_lead",
            "report_author",
            "techqa_by",
            "presqa_by",
            "timeslots",
            "job",
            "job__client",
        )
    )

    if can_scope:
        context["pendingScoping"] = list(
            Job.objects.filter(
                Q(unit__in=units_can_scope),
                Q(status=JobStatuses.PENDING_SCOPE)
                | Q(status=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
                | Q(status=JobStatuses.SCOPING),
            ).prefetch_related("unit", "client", "phases", "scoped_by")
        )
    else:
        context["pendingScoping"] = []

    if can_signoff_scope:
        context["scopesToSignoff"] = list(
            Job.objects.filter(
                Q(unit__in=units_can_signoff),
                status=JobStatuses.PENDING_SCOPING_SIGNOFF,
            ).prefetch_related("unit", "client", "phases")
        )
    else:
        context["scopesToSignoff"] = []

    if is_people_mgr:
        context["team"] = User.objects.filter(
            Q(manager=request.user) | Q(acting_manager=request.user),
            is_active=True,
        )
        context["team_leave"] = LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        ).select_related("user")

    if can_deliver:
        context["pendingDelivery"] = list(
            Phase.objects.filter(
                Q(job__unit__in=units_can_deliver),
                Q(status=PhaseStatuses.COMPLETED)
            ).prefetch_related("job__unit", "job__client")
        )
    else:
        context["pendingDelivery"] = []

    context = {**context, **page_defaults(request)}
    template = loader.get_template("dashboard_index.html")
    return HttpResponse(template.render(context, request))
