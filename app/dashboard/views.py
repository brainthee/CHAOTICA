from django.http import HttpResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from django.utils import timezone
from datetime import datetime, timedelta
from jobtracker.models import Job, Phase, TimeSlot
from chaotica_utils.models import LeaveRequest
from jobtracker.enums import JobStatuses, PhaseStatuses
from chaotica_utils.views import page_defaults
from django.db.models import Q
from django.views.decorators.http import require_safe

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

    context["in_flight"] = (
        Phase.objects.phases_with_unit_permission(request.user, "can_view_jobs")
        .filter(Q(status=PhaseStatuses.IN_PROGRESS))
        .order_by("desired_delivery_date")
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
    context["scheduled_phases_this_week"] = Phase.objects.phases_with_unit_permission(
        request.user, "can_view_jobs"
    ).filter(pk__in=phases_this_week)

    context["pendingScoping"] = Job.objects.jobs_with_unit_permission(
        request.user, "can_scope_jobs"
    ).filter(
        Q(status=JobStatuses.PENDING_SCOPE)
        | Q(status=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
    )

    context["scopesToSignoff"] = Job.objects.jobs_with_unit_permission(
        request.user, "can_signoff_scopes"
    ).filter(status=JobStatuses.PENDING_SCOPING_SIGNOFF)

    context["TQA"] = (
        Phase.objects.phases_with_unit_permission(request.user, "can_tqa_jobs")
        .filter(
            Q(status=PhaseStatuses.PENDING_TQA)
            | Q(status=PhaseStatuses.QA_TECH)
            | Q(status=PhaseStatuses.QA_TECH_AUTHOR_UPDATES)
        )
        .order_by("desired_delivery_date")
    )

    context["PQA"] = (
        Phase.objects.phases_with_unit_permission(request.user, "can_pqa_jobs")
        .filter(
            Q(status=PhaseStatuses.PENDING_PQA)
            | Q(status=PhaseStatuses.QA_PRES)
            | Q(status=PhaseStatuses.QA_PRES_AUTHOR_UPDATES)
        )
        .order_by("desired_delivery_date")
    )

    if request.user.is_people_manager():
        context["leaveToReview"] = LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        )
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))
