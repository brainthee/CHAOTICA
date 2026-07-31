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
from .forms import RMSyncRecordForm, RMUnitMapForm
from chaotica_utils.decorators import permission_required_or_403
from .models import *
from .enums import RMSyncDirection
from .tasks import task_sync_rm_schedule
from chaotica_utils.models import User
from jobtracker.models import OrganisationalUnit
from django.db.models import Count
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
    # Per-market-unit user counts, to annotate the Unit Maps table.
    mu_counts = {
        row["market_unit"]: row["n"]
        for row in RMSyncRecord.objects.exclude(market_unit="")
        .values("market_unit")
        .annotate(n=Count("pk"))
    }
    unit_maps = list(RMUnitMap.objects.select_related("unit").all())
    for m in unit_maps:
        m.user_count = mu_counts.get(m.market_unit, 0)

    context = {
        "rm_read_only": config.RM_SYNC_READ_ONLY,
        "rm_pull_enabled": config.RM_SYNC_PULL_ENABLED,
        "rm_unit_map_count": RMUnitMap.objects.filter(enabled=True).count(),
        "unit_maps": unit_maps,
        "org_units": OrganisationalUnit.objects.all().order_by("name"),
        "directions": RMSyncDirection.CHOICES,
        # Users being synced (read-only view); direction/OU are driven by Unit Maps.
        "sync_records": RMSyncRecord.objects.select_related("user")
        .prefetch_related("user__unit_memberships__unit")
        .order_by("-direction", "market_unit", "user__email"),
    }
    template = loader.get_template("rm_sync_settings.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_http_methods(["POST"])
def rm_update_unit_map(request, pk):
    """AJAX inline-save of a market-unit → OU + direction + enabled mapping."""
    umap = get_object_or_404(RMUnitMap, pk=pk)
    form = RMUnitMapForm(request.POST, instance=umap)
    data = {"form_is_valid": False}
    if form.is_valid():
        form.save()
        data["form_is_valid"] = True
        data["changed_data"] = form.changed_data
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_safe
def rm_import_users(request):
    """Adopt existing + create missing RM users (writes to CHAOTICA only; RM-read-only safe)."""
    from .users import import_rm_users

    r = import_rm_users(create_missing=True)
    messages.info(
        request,
        "Imported RM users — matched {}, created {}, {} new unit map(s), rm_id set {}, "
        "direction changed {} (protected {}). Set OU+direction on any new maps, then Apply.".format(
            r.matched,
            r.created,
            r.maps_created,
            r.rm_id_set,
            r.direction_set,
            r.direction_protected,
        ),
    )
    return HttpResponseRedirect(reverse("rm_settings"))


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_safe
def rm_apply_maps(request):
    from .users import apply_rm_unit_maps

    r = apply_rm_unit_maps()
    messages.info(
        request,
        "Applied unit maps — {} records, OU set {}, direction set {} (protected {}).".format(
            r.records, r.ou_set, r.direction_set, r.direction_protected
        ),
    )
    return HttpResponseRedirect(reverse("rm_settings"))


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_safe
def rm_import_clients(request):
    from .clients import sync_rm_clients

    r = sync_rm_clients()
    messages.info(
        request,
        "Imported RM clients — created {}, linked {}, skipped (no name) {}.".format(
            r.created, r.linked, r.skipped_no_name
        ),
    )
    return HttpResponseRedirect(reverse("rm_settings"))


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
def rm_pull_preview(request):
    """Dry-run the inbound (PULL) sync and report what *would* change. Writes nothing."""
    from .client import RMClient
    from .enums import RMSyncDirection
    from .users import sync_rm_users

    client = RMClient()
    users_res = sync_rm_users(client=client, dry_run=True)
    totals = {}
    for record in RMSyncRecord.objects.filter(direction=RMSyncDirection.PULL):
        res = record.pull_records(client=client, dry_run=True)
        for k in (
            "created_projects",
            "created_slots",
            "created_leave",
            "updated_slots",
            "deleted_slots",
            "skipped_chaotica_origin",
            "skipped_unresolved",
            "errors",
        ):
            totals[k] = totals.get(k, 0) + getattr(res, k)

    messages.info(
        request,
        "Dry-run — users: {} matched / +{} create / {} new unit map(s). "
        "Schedule: +{} projects, +{} slots, +{} leave, -{} deleted, {} errors.".format(
            users_res.matched,
            users_res.created,
            users_res.maps_created,
            totals.get("created_projects", 0),
            totals.get("created_slots", 0),
            totals.get("created_leave", 0),
            totals.get("deleted_slots", 0),
            totals.get("errors", 0),
        ),
    )
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
