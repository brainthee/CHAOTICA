from django.conf import settings
from constance import config
from django.template import loader
from django.utils import timezone
from django.http import (
    HttpResponse,
    JsonResponse,
    HttpResponseRedirect,
)
from django.urls import reverse
from .forms import RMSyncRecordForm
from guardian.decorators import permission_required_or_403
from .models import *
from .tasks import task_sync_rm_schedule
from chaotica_utils.models import User
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.views.decorators.http import (
    require_safe,
    require_http_methods,
)
from chaotica_utils.views import page_defaults


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_safe
def rm_settings(request):
    context = {
        "sync_records": RMSyncRecord.objects.all(),
        "all_users": User.objects.filter(is_active=True).order_by(
            "-rm_sync_record__sync_enabled", "-rm_sync_record__sync_authoritative"
        ),
    }
    template = loader.get_template("rm_sync_settings.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_safe
def rm_run_sync(request):
    # Check if we're enabled first...
    if not config.RM_SYNC_ENABLED:
        # RM Sync is disabled. Don't run        
        messages.warning(request, "RM Sync disabled")
        return HttpResponseRedirect(reverse("rm_settings"))
        
    if RMTaskLock.objects.filter(task_id=task_sync_rm_schedule.code).exists():
        # Task already in flight. Ignore this run
        messages.warning(request, "RM Sync already running")
        return HttpResponseRedirect(reverse("rm_settings"))
    
    task_sync_rm_schedule.do(request)
    messages.info(request, "Sync Running...")
    return HttpResponseRedirect(reverse("rm_settings"))


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_safe
def rm_clear_projects(request):    
    # Check if we're enabled first...
    if not config.RM_SYNC_ENABLED:
        # RM Sync is disabled. Don't run        
        messages.warning(request, "RM Sync disabled")
        return HttpResponseRedirect(reverse("rm_settings"))

    for sync_record in RMAssignableSlot.objects.all():
        sync_record.delete_in_rm()
        sync_record.delete()
    for sync_record in RMAssignable.objects.all():
        sync_record.delete_in_rm()
        sync_record.delete()
        
    messages.info(request, "Clear Sync Running...")
    return HttpResponseRedirect(reverse("rm_settings"))


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_http_methods(["GET", "POST"])
def rm_update_record(request):
    context = {}
    data = dict()
    if request.method == "POST":
        if request.POST.get("user") and int(request.POST.get("user")):
            user_pk = int(request.POST.get("user"))
            if RMSyncRecord.objects.filter(user__pk=user_pk).exists():
                form = RMSyncRecordForm(
                    request.POST, instance=RMSyncRecord.objects.get(user__pk=user_pk)
                )
            else:
                form = RMSyncRecordForm(request.POST)
        else:
            form = RMSyncRecordForm(request.POST)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
        else:
            data["form_is_valid"] = False
    return JsonResponse(data)