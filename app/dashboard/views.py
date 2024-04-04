from django.http import HttpResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from jobtracker.models import Job
from chaotica_utils.models import LeaveRequest
from jobtracker.enums import JobStatuses
from chaotica_utils.views import page_defaults
from django.db.models import Q
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@login_required
@require_safe
def index(request):
    context = {}
    template = loader.get_template("dashboard_index.html")
    context["pendingScoping"] = Job.objects.jobs_with_unit_permission(
        request.user, "can_scope_jobs"
    ).filter(status=JobStatuses.PENDING_SCOPE)
    context["scopesToSignoff"] = Job.objects.jobs_with_unit_permission(
        request.user, "can_signoff_scopes"
    ).filter(status=JobStatuses.PENDING_SCOPING_SIGNOFF)
    if request.user.is_people_manager():
        context["leaveToReview"] = LeaveRequest.objects.filter(
            Q(user__manager=request.user) | Q(user__acting_manager=request.user)
        )
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))
