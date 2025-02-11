from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import logging
from django.urls import reverse
from django.views.decorators.http import require_safe
from ..tasks import *
from django.contrib import messages

logger = logging.getLogger(__name__)


@login_required
@staff_member_required
@require_safe
def admin_task_update_phase_dates(request):
    task_update_phase_dates().do()
    messages.success(request, "Phase dates updated")
    return HttpResponseRedirect(reverse("home"))


@login_required
@staff_member_required
@require_safe
def admin_task_sync_global_permissions(request):
    task_sync_global_permissions()
    messages.success(request, "Global permissions sync'd")
    return HttpResponseRedirect(reverse("home"))


@login_required
@staff_member_required
@require_safe
def admin_task_sync_role_permissions_to_default(request):
    task_sync_role_permissions_to_default()
    messages.success(request, "Role Permissions sync'd to default")
    return HttpResponseRedirect(reverse("home"))


@login_required
@staff_member_required
@require_safe
def admin_task_sync_role_permissions(request):
    task_sync_role_permissions()
    messages.success(request, "Role Permissions sync'd")
    return HttpResponseRedirect(reverse("home"))