from django.http import HttpResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from jobtracker.models import Job,Phase
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

    context["pendingScoping"] = Job.objects.jobs_with_unit_permission(
        request.user, "can_scope_jobs"
    ).filter(Q(status=JobStatuses.PENDING_SCOPE) | Q(status=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED))

    context["scopesToSignoff"] = Job.objects.jobs_with_unit_permission(
        request.user, "can_signoff_scopes"
    ).filter(status=JobStatuses.PENDING_SCOPING_SIGNOFF)

    context["pendingTQA"] = Phase.objects.phases_with_unit_permission(
        request.user, "can_tqa_jobs"
    ).filter(status=PhaseStatuses.PENDING_TQA)

    context["pendingPQA"] = Phase.objects.phases_with_unit_permission(
        request.user, "can_pqa_jobs"
    ).filter(status=PhaseStatuses.PENDING_PQA)

    if request.user.is_people_manager():
        context["leaveToReview"] = LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        )
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))
