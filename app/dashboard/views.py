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

    all_phases = Phase.objects.filter(
        Q(
            job__unit__in=get_objects_for_user(
                request.user, "can_view_jobs", klass=OrganisationalUnit
            )
        ),
        status__in=PhaseStatuses.ACTIVE_STATUSES,  # Include active phase statuses only
        job__status__in=JobStatuses.ACTIVE_STATUSES,  # Include active job statuses only
    )

    context["myJobs"] = Job.objects.jobs_for_user(request.user)
    context["myPhases"] = Phase.objects.phases_for_user(request.user)

    context["in_flight"] = all_phases.filter(
        Q(status=PhaseStatuses.IN_PROGRESS)
    ).prefetch_related(
        "service",
        "job__client",
        "project_lead",
        "report_author",
    )
    context["TQA"] = (
        all_phases.filter(
            Q(status=PhaseStatuses.PENDING_TQA)
            | Q(status=PhaseStatuses.QA_TECH)
            | Q(status=PhaseStatuses.QA_TECH_AUTHOR_UPDATES)
        )
        .exclude(
            Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0)
        )  # Exclude non QA reports
        .prefetch_related(
            "service",
            "job__client",
            "project_lead",
            "report_author",
            "techqa_by",
        )
    )
    context["PQA"] = (
        all_phases.filter(
            Q(status=PhaseStatuses.PENDING_PQA)
            | Q(status=PhaseStatuses.QA_PRES)
            | Q(status=PhaseStatuses.QA_PRES_AUTHOR_UPDATES)
        )
        .exclude(
            Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0)
        )  # Exclude non QA reports
        .prefetch_related(
            "service",
            "job__client",
            "project_lead",
            "report_author",
            "presqa_by",
        )
    )

    twoweeks = get_start_of_week() + timedelta(weeks=2)
    context["upcoming_reports_date"] = twoweeks
    context["upcoming_reports"] = (
        all_phases.annotate(
            db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date")
        )
        .filter(Q(status__lt=PhaseStatuses.DELIVERED) & Q(db_delivery_date__lte=twoweeks))
        .exclude(
            Q(report_to_be_left_on_client_site=True) | Q(number_of_reports=0)
        )  # Exclude non QA reports
        .prefetch_related(
            "service",
            "job__client",
            "project_lead",
            "report_author",
            "presqa_by",
        )
    )

    context["scheduled_phases_this_week"] = (
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

    context["pendingScoping"] = Job.objects.filter(
        Q(
            unit__in=get_objects_for_user(
                request.user, "can_scope_jobs", klass=OrganisationalUnit
            )
        ),
        Q(status=JobStatuses.PENDING_SCOPE)
        | Q(status=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
        | Q(status=JobStatuses.SCOPING),
    ).prefetch_related("unit", "client", "phases", "scoped_by")

    context["scopesToSignoff"] = Job.objects.filter(
        Q(
            unit__in=get_objects_for_user(
                request.user, "can_signoff_scopes", klass=OrganisationalUnit
            )
        ),
        status=JobStatuses.PENDING_SCOPING_SIGNOFF,
    ).prefetch_related("unit", "client", "phases")

    if request.user.is_people_manager():
        context["team"] = User.objects.filter(
            Q(manager=request.user) | Q(acting_manager=request.user),
            is_active=True,
        )
        context["team_leave"] = LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        )

    context = {**context, **page_defaults(request)}
    template = loader.get_template("dashboard_index.html")
    return HttpResponse(template.render(context, request))
