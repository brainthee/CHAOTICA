from django.http import HttpResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from django.utils import timezone
from datetime import datetime, timedelta
from jobtracker.models import Job, Phase, TimeSlot, OrganisationalUnit
from chaotica_utils.models import LeaveRequest
from jobtracker.enums import JobStatuses, PhaseStatuses
from chaotica_utils.views import page_defaults
from django.db.models import Q
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
    template = loader.get_template("dashboard_index.html")

    view_units = get_objects_for_user(request.user, "can_view_jobs", klass=OrganisationalUnit)
    all_phases = Phase.objects.filter(
            Q(job__unit__in=view_units),
            status__in=PhaseStatuses.ACTIVE_STATUSES,  # Include active phase statuses only
            job__status__in=JobStatuses.ACTIVE_STATUSES,  # Include active job statuses only
        ).prefetch_related()

    context["in_flight"] = all_phases.filter(Q(status=PhaseStatuses.IN_PROGRESS))
    context["TQA"] = all_phases.filter(
            Q(status=PhaseStatuses.PENDING_TQA)
            | Q(status=PhaseStatuses.QA_TECH)
            | Q(status=PhaseStatuses.QA_TECH_AUTHOR_UPDATES)
        )
    context["PQA"] = all_phases.filter(
            Q(status=PhaseStatuses.PENDING_PQA)
            | Q(status=PhaseStatuses.QA_PRES)
            | Q(status=PhaseStatuses.QA_PRES_AUTHOR_UPDATES)
        )
    
    # this week's timeslots
    week_start_date = timezone.datetime.today() - timedelta(
        days=timezone.datetime.today().weekday()
    )
    week_end_date = week_start_date + timedelta(days=6)
    phases_this_week = (
        TimeSlot.objects.filter(
            end__gte=week_start_date, start__lte=week_end_date, phase__isnull=False
        )
        .values_list("phase", flat=True)
        .distinct()
    )
    context["scheduled_phases_this_week"] = all_phases.filter(pk__in=phases_this_week)


    scope_units = get_objects_for_user(request.user, "can_scope_jobs", klass=OrganisationalUnit)
    signoff_units = get_objects_for_user(request.user, "can_signoff_scopes", klass=OrganisationalUnit)

    context["pendingScoping"] = Job.objects.filter(
        Q(unit__in=scope_units),
        Q(status=JobStatuses.PENDING_SCOPE)
        | Q(status=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
    )

    context["scopesToSignoff"] = Job.objects.filter(
        Q(unit__in=signoff_units),
        status=JobStatuses.PENDING_SCOPING_SIGNOFF)

    if request.user.is_people_manager():
        context["leaveToReview"] = LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        )
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))
