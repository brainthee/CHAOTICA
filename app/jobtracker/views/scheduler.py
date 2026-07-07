from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, QueryDict
from django.template import loader
from django.db.models import Q, Prefetch
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_POST
from chaotica_utils.views import page_defaults
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.views import log_system_activity
from chaotica_utils.models import User
from guardian.shortcuts import get_objects_for_user
from ..models import (
    Job,
    TimeSlot,
    UserSkill,
    Phase,
    OrganisationalUnitMember,
    Project,
    OrganisationalUnitRole,
    TimeSlotComment,
)
from ..decorators import unit_permission_required_or_403, job_permission_required_or_403
from ..forms import (
    NonDeliveryTimeSlotModalForm,
    SchedulerFilter,
    ChangeTimeSlotDateModalForm,
    DeliveryTimeSlotModalForm,
    ProjectTimeSlotModalForm,
    CommentTimeSlotModalForm,
    ChangeTimeSlotCommentDateModalForm,
    MoveScheduleSlotsForm,
    ScheduleShiftForm,
    ScheduleSwapForm,
    ScheduleOnsiteForm,
)
from ..enums import UserSkillRatings, TimeSlotDeliveryRole, PhaseStatuses, DefaultTimeSlotTypes
from ..models import ScheduleAction, ScheduleActionType
from ..utils import (
    get_scheduler_slots,
    get_scheduler_members,
    assigned_role_map,
    can_view_job_schedule,
    viewable_schedule_user_pks,
)
from .. import schedule_history
import logging
from django.contrib.auth.decorators import login_required
from chaotica_utils.utils import (
    clean_int,
    clean_datetime,
    clean_fullcalendar_datetime,
    datetime_startofday,
    datetime_endofday,
)
from chaotica_utils.models import Holiday
from django.contrib import messages
from django.utils.html import escape
import time
from constance import config


logger = logging.getLogger(__name__)


def _slot_units(slot):
    """Resolve the org unit(s) that govern scheduling permission for a slot.

    Delivery slots → the job's unit; project slots → the project's unit; comment
    and internal / leave slots (which have neither phase nor project) → the units
    the slot's *user* belongs to. Returns a list (possibly empty)."""
    if getattr(slot, "phase", None):
        return [slot.phase.job.unit] if slot.phase.job.unit else []
    if getattr(slot, "project", None):
        unit = getattr(slot.project, "unit", None)
        return [unit] if unit else []
    # Comment / internal slot — governed by the slot user's unit memberships.
    user = getattr(slot, "user", None)
    if user is not None:
        return [m.unit for m in user.unit_memberships.select_related("unit").all()]
    return []


def _verify_slot_unit_access(request, slot):
    """Verify the requesting user may schedule the slot's governing unit(s).

    Covers TimeSlot (phase / project / internal) and TimeSlotComment (user-only).
    Raises PermissionDenied when the slot is governed by unit(s) the user cannot
    schedule. Mirrors the per-resource check in ``clear_scheduler_range``."""
    units = _slot_units(slot)
    if units and not any(
        request.user.has_perm("jobtracker.can_schedule_job", u) for u in units
    ):
        raise PermissionDenied


def _verify_unit_schedulable(request, unit):
    """Raise PermissionDenied unless the user can schedule the given unit.

    Used by the job/project create paths: the ``@unit_permission_required_or_403``
    decorator only proves the caller can schedule *some* unit, so the target
    job/project unit taken from request params must be re-verified here."""
    if unit and not request.user.has_perm("jobtracker.can_schedule_job", unit):
        raise PermissionDenied


def _verify_users_schedulable(request, users):
    """Raise PermissionDenied unless the user can schedule every target user's
    unit(s). For user-owned slots (internal / leave / comment) that aren't tied
    to a job or project. Mirrors ``clear_scheduler_range``'s per-resource check."""
    for resource in users:
        units = [m.unit for m in resource.unit_memberships.select_related("unit").all()]
        if units and not any(
            request.user.has_perm("jobtracker.can_schedule_job", u) for u in units
        ):
            raise PermissionDenied


def _check_framework_slot(framework, updated_slot, old_slot, request, force=False):
    """Check framework constraints (closed, over-allocation) for a modified slot.
    Returns a data dict if blocked, or None if OK."""
    if framework.closed:
        return {
            "form_is_valid": False,
            "logic_checks_failed": True,
            "logic_checks_can_bypass": False,
            "logic_checks_feedback": loader.render_to_string(
                "partials/scheduler/logicchecks/framework_closed.html",
                {"framework": framework},
                request=request,
            ),
        }
    hours_in_day = framework.get_hours_in_day()
    old_days = round(old_slot.get_business_hours() / hours_in_day, 1) if hours_in_day else 0
    new_days = round(updated_slot.get_business_hours() / hours_in_day, 1) if hours_in_day else 0
    days_allocated = framework.days_allocated()
    new_total = days_allocated - old_days + new_days
    if new_total > framework.total_days:
        if not framework.allow_over_allocation:
            return {
                "form_is_valid": False,
                "logic_checks_failed": True,
                "logic_checks_can_bypass": False,
                "logic_checks_feedback": loader.render_to_string(
                    "partials/scheduler/logicchecks/framework_over_allocated.html",
                    {
                        "framework": framework,
                        "days_allocated": days_allocated - old_days,
                        "slot_days": new_days,
                        "new_total": new_total,
                    },
                    request=request,
                ),
            }
        elif not force:
            return {
                "form_is_valid": False,
                "logic_checks_failed": True,
                "logic_checks_can_bypass": True,
                "logic_checks_feedback": loader.render_to_string(
                    "partials/scheduler/logicchecks/framework_over_budget_warning.html",
                    {
                        "framework": framework,
                        "days_allocated": days_allocated - old_days,
                        "slot_days": new_days,
                        "new_total": new_total,
                    },
                    request=request,
                ),
            }
    return None


def _check_phase_scoped(slot, request, force=False, old_slot=None):
    """Check if scheduling this slot would exceed the phase's scoped hours
    for the slot's delivery role. Returns a data dict if warning needed, or None if OK.
    This is a bypassable warning — schedulers can force-save."""
    phase = slot.phase
    if not phase or not slot.deliveryRole:
        return None

    scoped_hours = phase.get_total_scoped_by_type(slot.deliveryRole)
    if scoped_hours <= 0:
        return None  # No scope set — nothing to warn about

    scheduled_hours = float(phase.get_total_scheduled_by_type(slot.deliveryRole))
    slot_hours = float(slot.get_business_hours())
    scoped_hours = float(scoped_hours)

    # For edits, subtract the old slot's hours to avoid double-counting
    if old_slot and old_slot.pk and old_slot.deliveryRole == slot.deliveryRole:
        scheduled_hours -= float(old_slot.get_business_hours())

    new_total_hours = scheduled_hours + slot_hours
    if new_total_hours <= scoped_hours:
        return None  # Within scope

    if force:
        return None  # User chose to bypass

    hours_in_day = float(phase.get_hours_in_day()) if phase.get_hours_in_day() else 0
    delivery_role_name = dict(TimeSlotDeliveryRole.CHOICES).get(
        slot.deliveryRole, "Unknown"
    )

    return {
        "form_is_valid": False,
        "logic_checks_failed": True,
        "logic_checks_can_bypass": True,
        "logic_checks_feedback": loader.render_to_string(
            "partials/scheduler/logicchecks/phase_over_scoped.html",
            {
                "phase": phase,
                "delivery_role_name": delivery_role_name,
                "scoped_hours": round(scoped_hours, 1),
                "scoped_days": round(scoped_hours / hours_in_day, 1) if hours_in_day else 0,
                "scheduled_hours": round(scheduled_hours, 1),
                "scheduled_days": round(scheduled_hours / hours_in_day, 1) if hours_in_day else 0,
                "slot_hours": round(slot_hours, 1),
                "slot_days": round(slot_hours / hours_in_day, 1) if hours_in_day else 0,
                "new_total_hours": round(new_total_hours, 1),
                "new_total_days": round(new_total_hours / hours_in_day, 1) if hours_in_day else 0,
            },
            request=request,
        ),
    }


def _check_onboarding(slot, request, force=False):
    """Enforce client onboarding for a delivery slot's assigned user.

    Returns a logic-check data dict (or None), mirroring the return shape of
    _check_phase_scoped so it drops into any slot create/change path.
    Non-bypassable if the user has no onboarding record for the client;
    a bypassable "stale" warning if their onboarding has lapsed."""
    if not slot.is_delivery() or not slot.phase:
        return None
    client = slot.phase.job.client
    if not client.onboarding_required:
        return None

    onboarding = client.onboarded_users.filter(user=slot.user).first()
    if onboarding is None:
        return {
            "form_is_valid": False,
            "logic_checks_failed": True,
            "logic_checks_can_bypass": False,
            "logic_checks_feedback": loader.render_to_string(
                "partials/scheduler/logicchecks/not_onboarded.html",
                {"slot": slot, "phase": slot.phase},
                request=request,
            ),
        }

    if onboarding.is_stale and not force:
        return {
            "form_is_valid": False,
            "logic_checks_failed": True,
            "logic_checks_can_bypass": True,
            "logic_checks_feedback": loader.render_to_string(
                "partials/scheduler/logicchecks/stale_onboarding.html",
                {"slot": slot, "phase": slot.phase},
                request=request,
            ),
        }
    return None


@login_required
def view_scheduler(request):
    saved = request.user.scheduler_default_filter
    # No explicit query + a saved default + not explicitly opting out -> apply default.
    # Any query string (bookmark, ?nofilter=1, or the ?_dv=1 we redirect to) skips this,
    # so there is no redirect loop.
    if not request.GET and saved:
        return redirect(f"{reverse('view_scheduler')}?{saved}&_dv=1")
    context = {"scheduler_scope": "global"}
    template = loader.get_template("scheduler.html")
    context = {**context, **page_defaults(request)}
    context["filter_form"] = SchedulerFilter(request.GET)
    context["has_default_filter"] = bool(saved)
    context["is_default_view"] = request.GET.get("_dv") == "1"
    return HttpResponse(template.render(context, request))


@login_required
def view_scheduler_slots(request):
    return get_scheduler_slots(request)


@login_required
def view_scheduler_members(request):
    return get_scheduler_members(request)


# Cap the stored filter to bound the redirect Location header / row size.
_MAX_DEFAULT_FILTER_LEN = 4000


@login_required
@require_POST
def set_scheduler_filter_default(request):
    """Persist the current scheduler filter as the user's default view.

    The raw POST is never stored: it is parsed through ``SchedulerFilter`` and
    re-serialised from only the form's declared fields with ``QueryDict.urlencode()``.
    This whitelists known fields and percent-encodes the result, so unknown/injected
    keys (``_dv``, ``nofilter``, CRLF/``#`` tricks) can never enter the stored value or
    the later auto-load redirect.
    """
    raw = request.POST.get("filter", "")[:_MAX_DEFAULT_FILTER_LEN]
    submitted = QueryDict(raw)
    form = SchedulerFilter(submitted)
    form.is_valid()
    clean = QueryDict(mutable=True)
    for name in form.fields:
        vals = submitted.getlist(name)
        if any(v for v in vals):
            clean.setlist(name, vals)
    request.user.scheduler_default_filter = clean.urlencode()
    request.user.save(update_fields=["scheduler_default_filter"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def clear_scheduler_filter_default(request):
    """Remove the user's saved default scheduler view."""
    request.user.scheduler_default_filter = ""
    request.user.save(update_fields=["scheduler_default_filter"])
    return JsonResponse({"ok": True})


def _scope_history_qs(request, source):
    """Filter the ScheduleAction log to the requested scope and authorise it.

    Returns ``(queryset, viewable_user_pks)``:
    - phase/job param → that scope, but only after ``view_job_schedule`` is
      confirmed on the job (returns an empty queryset otherwise, so a caller can
      never read a job/phase they may not see). ``viewable_user_pks`` is ``None``
      (whole scope already authorised).
    - neither → recent global activity; ``viewable_user_pks`` is the set of users
      whose slots the requester may see, so the delta layer can filter payloads."""
    job_id = clean_int(source.get("job"))
    phase_id = clean_int(source.get("phase"))
    qs = ScheduleAction.objects.select_related("actor").order_by("-created")
    if phase_id:
        phase = Phase.objects.select_related("job__unit").filter(pk=phase_id).first()
        if not phase or not can_view_job_schedule(request.user, phase.job):
            return qs.none(), None
        return qs.filter(phase_id=phase_id), None
    if job_id:
        job = Job.objects.select_related("unit").filter(pk=job_id).first()
        if not job or not can_view_job_schedule(request.user, job):
            return qs.none(), None
        return qs.filter(job_id=job_id), None
    return qs, viewable_schedule_user_pks(request.user)


@login_required
def schedule_action_history(request):
    """History panel data: the ScheduleAction log for the current scope, newest
    first, with a per-action ``can_revert`` computed for the requesting user."""
    qs, _viewable = _scope_history_qs(request, request.GET)
    qs = qs[:100]
    actions = []
    for a in qs:
        actions.append(
            {
                "id": a.pk,
                "actor": a.actor.get_full_name() if a.actor else "System",
                "actor_id": a.actor_id,
                "created": a.created.isoformat(),
                "action_type": a.action_type,
                "summary": a.summary,
                "reverted": a.reverted,
                "is_revert": a.action_type == ScheduleActionType.REVERT,
                "can_revert": a.can_revert(request.user),
            }
        )
    return JsonResponse({"actions": actions})


@login_required
def schedule_action_revert(request):
    """Revert a single ScheduleAction (pk in POST body)."""
    if request.method != "POST":
        return HttpResponseBadRequest()
    pk = clean_int(request.POST.get("pk"))
    action = get_object_or_404(ScheduleAction, pk=pk)
    try:
        inverse = schedule_history.revert(action, request.user)
    except PermissionDenied:
        return JsonResponse(
            {"ok": False, "error": "You don't have permission to revert this change."},
            status=403,
        )
    return JsonResponse({"ok": True, "action_id": inverse.pk if inverse else None})


@login_required
def schedule_action_undo(request):
    """Ctrl+Z: revert the requesting user's most-recent non-reverted own change in
    this scope. REVERT actions are excluded so undo walks back through real edits
    (redo is available from the history panel)."""
    if request.method != "POST":
        return HttpResponseBadRequest()
    qs, _viewable = _scope_history_qs(request, request.POST)
    qs = qs.filter(actor=request.user, reverted=False).exclude(
        action_type=ScheduleActionType.REVERT
    )
    action = qs.first()
    if not action:
        return JsonResponse({"ok": False, "error": "Nothing to undo."})
    try:
        inverse = schedule_history.revert(action, request.user)
    except PermissionDenied:
        return JsonResponse(
            {"ok": False, "error": "You can no longer schedule this work, so it can't be undone."},
            status=403,
        )
    return JsonResponse(
        {"ok": True, "reverted": action.pk, "action_id": inverse.pk if inverse else None}
    )


@login_required
def view_scheduler_slots_since(request):
    """Polling fallback for the live layer: return ScheduleAction deltas committed
    to this scope since ``since`` (ISO), chronological, so a client without a live
    WebSocket can still apply add/update/remove deltas instead of full reloads."""
    from django.utils import timezone as _tz

    since = clean_datetime(request.GET.get("since"))
    qs, viewable = _scope_history_qs(request, request.GET)
    if since:
        qs = qs.filter(created__gt=since)
    actions = list(qs[:200])
    deltas = [
        schedule_history.filter_delta_for_users(
            schedule_history.build_delta(a), viewable
        )
        for a in reversed(actions)
    ]
    return JsonResponse({"deltas": deltas, "now": _tz.now().isoformat()})


@login_required
def view_own_schedule_timeslots(request):
    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    data = request.user.get_timeslots(
        start=start,
        end=end,
    )
    return JsonResponse(data, safe=False)


@login_required
def view_own_schedule_holidays(request):
    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    data = request.user.get_holidays(
        start=start,
        end=end,
    )
    return JsonResponse(data, safe=False)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def change_scheduler_slot_comment_date(request, pk=None):
    """Changes the date of the specified timeslotcomment. Used when we don't care what the type is.

    Args:
        request (Django request): Django request
        pk (int, optional): PK of the TimeSlot. Not actually optional but made options so we can append the PK in JS client-side.

    Returns:
        _type_: JSONResponse
    """
    if not pk:
        # We only do this because we want to generate the URL in JS land
        return HttpResponseBadRequest()
    slot = get_object_or_404(TimeSlotComment, pk=pk)
    _verify_slot_unit_access(request, slot)
    data = dict()
    if request.method == "POST":
        before = schedule_history.snapshot_comment(slot)
        form = ChangeTimeSlotCommentDateModalForm(request.POST, instance=slot)
        if form.is_valid():
            comment = form.save()
            schedule_history.record(
                request.user, ScheduleActionType.UPDATE,
                [before], [schedule_history.snapshot_comment(comment)],
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = ChangeTimeSlotCommentDateModalForm(instance=slot)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def change_scheduler_slot_comment(request, pk=None):
    """Changes a TimeSlot entry. Returns different forms based on the type of TimeSlot

    Args:
        request (_type_): _description_
        pk (_type_, optional): PK of the TimeSlot. Optional to allow clientside construction

    Returns:
        JsonResponse: _description_
    """
    if not pk:
        # We only do this because we want to generate the URL in JS land
        return HttpResponseBadRequest()
    slot = get_object_or_404(TimeSlotComment, pk=pk)
    _verify_slot_unit_access(request, slot)
    data = dict()
    if request.method == "POST":
        before = schedule_history.snapshot_comment(slot)
        form = CommentTimeSlotModalForm(request.POST, instance=slot)

        if form.is_valid():
            comment = form.save()
            schedule_history.record(
                request.user, ScheduleActionType.UPDATE,
                [before], [schedule_history.snapshot_comment(comment)],
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = CommentTimeSlotModalForm(instance=slot)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot_comment.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def change_scheduler_slot_date(request, pk=None):
    """Changes the date of the specified timeslot. Used when we don't care what the type is.

    Args:
        request (Django request): Django request
        pk (int, optional): PK of the TimeSlot. Not actually optional but made options so we can append the PK in JS client-side.

    Returns:
        _type_: JSONResponse
    """
    if not pk:
        # We only do this because we want to generate the URL in JS land
        return HttpResponseBadRequest()
    slot = get_object_or_404(TimeSlot, pk=pk)
    _verify_slot_unit_access(request, slot)
    # Leave / time off (non-working slots) is managed via leave requests, not the
    # scheduler — refuse to move or edit it here.
    if not slot.slot_type.is_working:
        return JsonResponse({
            "form_is_valid": False,
            "error": "Leave / time off can't be moved from the scheduler — manage it via the leave request.",
        })
    data = dict()
    if request.method == "POST":
        before = schedule_history.snapshot(slot)
        force = request.POST.get("force", None)
        form = ChangeTimeSlotDateModalForm(request.POST, instance=slot)
        if form.is_valid():
            updated_slot = form.save(commit=False)
            # Framework checks for delivery slots
            if updated_slot.is_delivery() and updated_slot.phase:
                framework = updated_slot.phase.job.associated_framework
                if framework:
                    _data = _check_framework_slot(framework, updated_slot, slot, request, force=force)
                    if _data:
                        _data["html_form"] = loader.render_to_string(
                            "jobtracker/modals/job_slot.html", {"form": form}, request=request
                        )
                        return JsonResponse(_data)
                _data = _check_phase_scoped(updated_slot, request, force=force, old_slot=slot)
                if _data:
                    _data["html_form"] = loader.render_to_string(
                        "jobtracker/modals/job_slot.html", {"form": form}, request=request
                    )
                    return JsonResponse(_data)
                # Non-bypassable if reassigning to a not-onboarded user (BUG-004)
                _data = _check_onboarding(updated_slot, request, force=force)
                if _data:
                    _data["html_form"] = loader.render_to_string(
                        "jobtracker/modals/job_slot.html", {"form": form}, request=request
                    )
                    return JsonResponse(_data)
            updated_slot.save()
            schedule_history.record(
                request.user, ScheduleActionType.UPDATE,
                [before], [schedule_history.snapshot(updated_slot)],
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = ChangeTimeSlotDateModalForm(instance=slot)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def change_scheduler_slot(request, pk=None):
    """Changes a TimeSlot entry. Returns different forms based on the type of TimeSlot

    Args:
        request (_type_): _description_
        pk (_type_, optional): PK of the TimeSlot. Optional to allow clientside construction

    Returns:
        JsonResponse: _description_
    """
    if not pk:
        # We only do this because we want to generate the URL in JS land
        return HttpResponseBadRequest()
    slot = get_object_or_404(TimeSlot, pk=pk)
    _verify_slot_unit_access(request, slot)
    # Leave / time off (non-working slots) is managed via leave requests, not the
    # scheduler — refuse to move or edit it here.
    if not slot.slot_type.is_working:
        return JsonResponse({
            "form_is_valid": False,
            "error": "Leave / time off can't be moved from the scheduler — manage it via the leave request.",
        })
    data = dict()

    if request.method == "POST":
        before = schedule_history.snapshot(slot)
        force = request.POST.get("force", None)
        if slot.is_delivery():
            form = DeliveryTimeSlotModalForm(request.POST, instance=slot)
        elif slot.is_project():
            form = ProjectTimeSlotModalForm(request.POST, instance=slot)
        else:
            form = NonDeliveryTimeSlotModalForm(request.POST, instance=slot)

        if form.is_valid():
            updated_slot = form.save(commit=False)
            # Framework checks for delivery slots
            if updated_slot.is_delivery() and updated_slot.phase:
                framework = updated_slot.phase.job.associated_framework
                if framework:
                    _data = _check_framework_slot(framework, updated_slot, slot, request, force=force)
                    if _data:
                        _data["html_form"] = loader.render_to_string(
                            "jobtracker/modals/job_slot.html", {"form": form}, request=request
                        )
                        return JsonResponse(_data)
                _data = _check_phase_scoped(updated_slot, request, force=force, old_slot=slot)
                if _data:
                    _data["html_form"] = loader.render_to_string(
                        "jobtracker/modals/job_slot.html", {"form": form}, request=request
                    )
                    return JsonResponse(_data)
                # Non-bypassable if reassigning to a not-onboarded user (BUG-004)
                _data = _check_onboarding(updated_slot, request, force=force)
                if _data:
                    _data["html_form"] = loader.render_to_string(
                        "jobtracker/modals/job_slot.html", {"form": form}, request=request
                    )
                    return JsonResponse(_data)
            updated_slot.save()
            schedule_history.record(
                request.user, ScheduleActionType.UPDATE,
                [before], [schedule_history.snapshot(updated_slot)],
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        if slot.is_delivery():
            form = DeliveryTimeSlotModalForm(instance=slot)
        elif slot.is_project():
            form = ProjectTimeSlotModalForm(instance=slot)
        else:
            form = NonDeliveryTimeSlotModalForm(instance=slot)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot.html", context, request=request
    )
    return JsonResponse(data)


########
## Timeslot Creation Methods


def _selected_users(request):
    """Resolve target users for a create/clear action. Supports batch via a
    `users` CSV param; falls back to a single `resource_id`. Order preserved."""
    raw = request.GET.get("batch_users") or request.POST.get("batch_users") or ""
    ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]
    if not ids:
        rid = clean_int(request.GET.get("resource_id") or request.POST.get("resource_id"))
        if rid:
            ids = [rid]
    by_pk = {u.pk: u for u in User.objects.filter(pk__in=ids)}
    return [by_pk[i] for i in ids if i in by_pk]


def _evaluate_delivery_slot(slot, request, force, check_overlaps=True):
    """Run all delivery-slot logic checks for ONE unsaved slot (no save).
    Mirrors the inline checks in create_scheduler_phase_slot.
    Set check_overlaps=False to skip the overlap branch (the single-user create
    path handles overlaps via the around/over/destructive chooser instead).
    Returns {"failed": bool, "can_bypass": bool, "feedback": str}."""
    result = {"failed": False, "can_bypass": True, "feedback": ""}
    slots = slot.overlapping_slots()
    framework = slot.phase.job.associated_framework

    # Non-bypassable: framework closed
    if framework and framework.closed:
        return {"failed": True, "can_bypass": False,
                "feedback": loader.render_to_string(
                    "partials/scheduler/logicchecks/framework_closed.html",
                    {"framework": framework}, request=request)}

    # Non-bypassable: framework over-allocation
    if framework and not framework.allow_over_allocation:
        slot_hours = slot.get_business_hours()
        hours_in_day = framework.get_hours_in_day()
        slot_days = round(slot_hours / hours_in_day, 1) if hours_in_day else 0
        days_allocated = framework.days_allocated()
        new_total = days_allocated + slot_days
        if new_total > framework.total_days:
            return {"failed": True, "can_bypass": False,
                    "feedback": loader.render_to_string(
                        "partials/scheduler/logicchecks/framework_over_allocated.html",
                        {"framework": framework, "days_allocated": days_allocated,
                         "slot_days": slot_days, "new_total": new_total}, request=request)}

    # Onboarding: non-bypassable if not onboarded, bypassable "stale" warning
    _onboard = _check_onboarding(slot, request, force=force)
    if _onboard:
        return {"failed": True, "can_bypass": _onboard["logic_checks_can_bypass"],
                "feedback": _onboard["logic_checks_feedback"]}

    # Bypassable checks (skipped entirely when forcing)
    if not force:
        _scoped = _check_phase_scoped(slot, request)
        if _scoped:
            result["failed"] = True
            result["can_bypass"] = True
            result["feedback"] += _scoped["logic_checks_feedback"]

        if framework and framework.allow_over_allocation:
            slot_hours = slot.get_business_hours()
            hours_in_day = framework.get_hours_in_day()
            slot_days = round(slot_hours / hours_in_day, 1) if hours_in_day else 0
            days_allocated = framework.days_allocated()
            new_total = days_allocated + slot_days
            if new_total > framework.total_days:
                result["failed"] = True
                result["can_bypass"] = True
                result["feedback"] += loader.render_to_string(
                    "partials/scheduler/logicchecks/framework_over_budget_warning.html",
                    {"framework": framework, "days_allocated": days_allocated,
                     "slot_days": slot_days, "new_total": new_total}, request=request)

        if check_overlaps and slots:
            if slots.filter(slot_type__is_working=False).exists():
                result["failed"] = True
                result["can_bypass"] = False
                result["feedback"] += loader.render_to_string(
                    "partials/scheduler/logicchecks/unavailable.html",
                    {"slot": slot, "unavailable_slots": slots.filter(slot_type__is_working=False)},
                    request=request)
            else:
                result["failed"] = True
                result["can_bypass"] = True
                result["feedback"] += loader.render_to_string(
                    "partials/scheduler/logicchecks/overlaps.html",
                    {"slot": slot, "overlapping_slots": slots}, request=request)
    return result


def _evaluate_project_slot(slot, request, force):
    """Overlap checks for ONE unsaved project slot (mirrors create_scheduler_project_slot)."""
    result = {"failed": False, "can_bypass": True, "feedback": ""}
    if force:
        return result
    slots = slot.overlapping_slots()
    if slots:
        if slots.filter(slot_type__is_working=False).exists():
            result["failed"] = True
            result["can_bypass"] = False
            result["feedback"] += loader.render_to_string(
                "partials/scheduler/logicchecks/unavailable.html",
                {"slot": slot, "unavailable_slots": slots.filter(slot_type__is_working=False)},
                request=request)
        else:
            result["failed"] = True
            result["can_bypass"] = True
            result["feedback"] += loader.render_to_string(
                "partials/scheduler/logicchecks/overlaps.html",
                {"slot": slot, "overlapping_slots": slots}, request=request)
    return result


def _run_batch_create(request, users, build_slot, evaluate, force):
    """Create one slot per user, running per-user `evaluate` checks.
    Returns the JsonResponse `data` dict. Single-user is the loop-of-one."""
    data = {"logic_checks_feedback": ""}
    batch = len(users) > 1
    evals = []
    for u in users:
        slot = build_slot(u)
        ev = evaluate(slot, request, force) if evaluate else {"failed": False, "can_bypass": True, "feedback": ""}
        evals.append((u, slot, ev))

    needs_confirm = [t for t in evals if t[2]["failed"] and t[2]["can_bypass"]]
    blocked = [t for t in evals if t[2]["failed"] and not t[2]["can_bypass"]]
    clean = [t for t in evals if not t[2]["failed"]]

    # First submit with outstanding bypassable warnings → ask to force.
    if needs_confirm and not force:
        data["form_is_valid"] = False
        data["logic_checks_failed"] = True
        data["logic_checks_can_bypass"] = True
        fb = ""
        if batch:
            fb += "<p>{} of {} selected people have warnings:</p>".format(
                len(needs_confirm), len(evals))
            if blocked:
                fb += "<p class='text-danger'>{} will be skipped (blocked): {}</p>".format(
                    len(blocked), escape(", ".join(str(u) for u, _, _ in blocked)))
        for u, _s, e in needs_confirm:
            if batch:
                fb += "<hr class='my-2'><strong>{}</strong>".format(escape(str(u)))
            fb += e["feedback"]
        data["logic_checks_feedback"] = fb
        return data

    # Save clean (+ forced bypassable); skip blocked.
    to_save = clean + (needs_confirm if force else [])
    for _u, s, _e in to_save:
        s.save()
    data["_saved_slots"] = [s for _u, s, _e in to_save]
    data["form_is_valid"] = True
    if batch:
        summary = "Booked {} {}.".format(len(to_save), "person" if len(to_save) == 1 else "people")
        if blocked:
            summary += " Skipped {} (blocked): {}.".format(
                len(blocked), ", ".join(str(u) for u, _, _ in blocked))
        data["summary"] = summary
    return data


def _record_created(request, data):
    """Log a CREATE ScheduleAction for slots saved by a create helper, popping the
    non-serialisable instance list out of the JSON response payload."""
    slots = data.pop("_saved_slots", None)
    if data.get("form_is_valid") and slots:
        schedule_history.record_creates(request.user, slots)


def _occupied_dates(user, start, end, slot_type_pks=None):
    """Set of calendar dates the user already has a slot on within [start, end]."""
    from datetime import timedelta
    dates = set()
    qs = user.get_timeslots_objs(start, end)
    if slot_type_pks is not None:
        qs = qs.filter(slot_type_id__in=slot_type_pks)
    for slot in qs:
        d, last = slot.start.date(), slot.end.date()
        while d <= last:
            dates.add(d)
            d += timedelta(days=1)
    return dates


def working_day_runs(user, start, end, occupied):
    """Runs of consecutive bookable working days in [start, end]. A day is
    bookable if it's a working day (org business days), not a holiday, and not in
    `occupied`. Non-working days DON'T break a run (a slot may span weekends); an
    occupied working day does. Returns [(run_start_date, run_end_date), ...]."""
    from datetime import timedelta
    org = user.unit_memberships.first()
    business_days = (
        org.unit.businessHours_days if org and org.unit.businessHours_days
        else [1, 2, 3, 4, 5]
    )
    holidays = set(
        Holiday.objects.filter(
            country=user.country, date__gte=start.date(), date__lte=end.date()
        ).values_list("date", flat=True)
    )
    runs = []
    run_start = run_end = None
    cur, last = start.date(), end.date()
    while cur <= last:
        # Their scheme: Sunday==0, Monday==1 … matches (weekday()+1) for Mon-Fri.
        if (cur.weekday() + 1) in business_days and cur not in holidays:
            if cur not in occupied:
                if run_start is None:
                    run_start = cur
                run_end = cur
            elif run_start is not None:
                runs.append((run_start, run_end))
                run_start = run_end = None
        cur += timedelta(days=1)
    if run_start is not None:
        runs.append((run_start, run_end))
    return runs


def _slot_dt(user, day, which):
    """Combine a date with the user's working start/end time (tz-aware)."""
    from datetime import datetime
    from django.utils import timezone
    wh = user.get_working_hours()
    t = wh["start"] if which == "start" else wh["end"]
    return datetime.combine(day, t).replace(tzinfo=timezone.get_current_timezone())


def _apply_phase_role_assignment(request, phase, user, form):
    """Set the scheduled user as the phase's project lead / report author when the
    booking modal's opt-in checkboxes are ticked. No-op if already assigned to them."""
    changed = []
    if form.cleaned_data.get("set_as_lead") and phase.project_lead_id != user.pk:
        phase.project_lead = user
        changed.append("Project Lead")
    if form.cleaned_data.get("set_as_author") and phase.report_author_id != user.pk:
        phase.report_author = user
        changed.append("Report Author")
    if changed:
        phase.save()
        log_system_activity(
            phase,
            "{} assigned as {} while scheduling".format(user, ", ".join(changed)),
            author=request.user,
        )


def _create_delivery_single(request, base, force):
    """Single-user delivery create with the overlap chooser (around/over/
    destructive). `base` is the unsaved slot for the whole requested range."""
    # Non-overlap pre-checks (framework / onboarding / phase-scope). Overlaps are
    # handled below via the chooser, so skip them here.
    ev = _evaluate_delivery_slot(base, request, force, check_overlaps=False)
    if ev["failed"] and not (force and ev["can_bypass"]):
        return {
            "form_is_valid": False,
            "logic_checks_failed": True,
            "logic_checks_can_bypass": ev["can_bypass"],
            "logic_checks_feedback": ev["feedback"],
        }

    overlaps = base.overlapping_slots()
    overlap_mode = request.POST.get("overlap_mode")

    if overlaps.exists() and not overlap_mode:
        counts = {
            "unavailable": overlaps.filter(slot_type__is_working=False).count(),
            "delivery": overlaps.filter(slot_type_id=DefaultTimeSlotTypes.DELIVERY).count(),
            "project": overlaps.filter(slot_type_id=DefaultTimeSlotTypes.INTERNAL_PROJECT).count(),
        }
        counts["internal"] = (
            overlaps.count() - counts["unavailable"] - counts["delivery"] - counts["project"]
        )
        return {
            "form_is_valid": False,
            "needs_overlap_choice": True,
            "logic_checks_failed": True,
            "logic_checks_feedback": loader.render_to_string(
                "partials/scheduler/logicchecks/overlap_choice.html",
                {"slot": base, "counts": counts}, request=request),
        }

    def _clone(day_start, day_end):
        return TimeSlot(
            user=base.user, phase=base.phase, slot_type=base.slot_type,
            deliveryRole=base.deliveryRole, is_onsite=base.is_onsite,
            start=day_start, end=day_end,
        )

    if overlap_mode == "around":
        occupied = _occupied_dates(base.user, base.start, base.end)
        runs = working_day_runs(base.user, base.start, base.end, occupied)
        saved = []
        for run_start, run_end in runs:
            clone = _clone(_slot_dt(base.user, run_start, "start"),
                           _slot_dt(base.user, run_end, "end"))
            clone.save()
            saved.append(clone)
        created = len(runs)
        return {
            "form_is_valid": True,
            "_saved_slots": saved,
            "summary": (
                "Booked {} slot{} around existing commitments.".format(created, "" if created == 1 else "s")
                if created else "No free working days in that range — nothing booked."
            ),
        }

    if overlap_mode == "destructive":
        base.user.clear_timeslots_in_range(
            base.start, base.end,
            slot_type_pks=[DefaultTimeSlotTypes.DELIVERY, DefaultTimeSlotTypes.INTERNAL_PROJECT],
        )
        base.save()
        return {
            "form_is_valid": True,
            "_saved_slots": [base],
            "summary": "Cleared overlapping delivery/project work and booked the range.",
        }

    # over (default) — book the whole range on top of existing slots
    base.save()
    return {"form_is_valid": True, "_saved_slots": [base]}


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def create_scheduler_internal_slot(request):
    """Creates an Internal type of TimeSlot

    Args:
        request (request): Django request

    Returns:
        JsonResponse: _description_
    """
    data = {"logic_checks_feedback": ""}
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))

    users = _selected_users(request)
    resource = users[0] if users else None

    # The decorator only proves the caller can schedule *some* unit; verify they
    # may schedule every target user's unit before creating slots for them.
    _verify_users_schedulable(request, users)

    if request.method == "POST":
        form = NonDeliveryTimeSlotModalForm(
            request.POST, start=start, end=end, resource=resource
        )
        if form.is_valid():
            base = form.save(commit=False)

            def build_slot(u):
                return TimeSlot(
                    user=u,
                    phase=base.phase,
                    project=base.project,
                    slot_type=base.slot_type,
                    deliveryRole=base.deliveryRole,
                    is_onsite=base.is_onsite,
                    start=base.start,
                    end=base.end,
                )

            # Internal/leave slots have no logic checks — straight batch create.
            data = _run_batch_create(request, users, build_slot, None, None)
            _record_created(request, data)
        else:
            data = {"form_is_valid": False}
    else:
        form = NonDeliveryTimeSlotModalForm(start=start, end=end, resource=resource)

    context = {"form": form, "batch_users": users if len(users) > 1 else None}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot_create.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def create_scheduler_project_slot(request):
    """Creates a Project type of TimeSlot

    Args:
        request (request): Django request

    Returns:
        JsonResponse: _description_
    """
    data = {"logic_checks_feedback": ""}
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))
    project_id = clean_int(request.GET.get("project", None))

    users = _selected_users(request)
    user = users[0] if users else None
    project = get_object_or_404(Project, pk=project_id) if project_id else None

    # Re-verify the target project's unit (the decorator only proves the caller
    # can schedule some unit).
    _verify_unit_schedulable(request, getattr(project, "unit", None))

    if request.method == "POST":
        force = request.POST.get("force", None)
        form = ProjectTimeSlotModalForm(
            request.POST,
            start=start,
            end=end,
            user=user,
            project=project,
        )
        if form.is_valid():
            base = form.save(commit=False)

            def build_slot(u):
                return TimeSlot(
                    user=u,
                    phase=base.phase,
                    project=base.project,
                    slot_type=base.slot_type,
                    deliveryRole=base.deliveryRole,
                    is_onsite=base.is_onsite,
                    start=base.start,
                    end=base.end,
                )

            data = _run_batch_create(request, users, build_slot, _evaluate_project_slot, force)
            _record_created(request, data)
        else:
            data = {"form_is_valid": False}
    else:
        form = ProjectTimeSlotModalForm(
            start=start,
            end=end,
            user=user,
            project=project,
        )

    context = {"form": form, "batch_users": users if len(users) > 1 else None}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/project_slot_create.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def create_scheduler_phase_slot(request):
    """Creates a Phase type of TimeSlot

    Args:
        request (request): Django request

    Returns:
        JsonResponse: _description_
    """
    data = {"logic_checks_feedback": ""}
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))
    job_id = clean_int(request.GET.get("job", None))
    phase_id = clean_int(request.GET.get("phase", None))

    users = _selected_users(request)
    user = users[0] if users else None

    if job_id:
        job = get_object_or_404(Job, pk=job_id)
        phase = get_object_or_404(Phase, pk=phase_id) if phase_id else None
    else:
        job = None
        phase = None

    # Re-verify the target job's unit — the decorator only proves the caller can
    # schedule some unit, and job/phase come from request params. Also guards the
    # phase-lead / report-author assignment side effect below.
    _verify_unit_schedulable(request, getattr(job, "unit", None))

    single = len(users) == 1
    if request.method == "POST":
        force = request.POST.get("force", None)
        form = DeliveryTimeSlotModalForm(
            request.POST, start=start, end=end, user=user, phase=phase, job=job, single=single
        )
        if form.is_valid():
            base = form.save(commit=False)

            if len(users) > 1:
                def build_slot(u):
                    return TimeSlot(
                        user=u,
                        phase=base.phase,
                        slot_type=base.slot_type,
                        deliveryRole=base.deliveryRole,
                        is_onsite=base.is_onsite,
                        start=base.start,
                        end=base.end,
                    )

                data = _run_batch_create(request, users, build_slot, _evaluate_delivery_slot, force)
            else:
                # Single resource → offer around / over / destructive on overlaps.
                data = _create_delivery_single(request, base, force)
                # Optionally assign the scheduled user as phase lead / report author.
                if data.get("form_is_valid") and base.phase_id and base.user_id:
                    _apply_phase_role_assignment(request, base.phase, base.user, form)
            _record_created(request, data)
        else:
            data = {"form_is_valid": False}
    else:
        form = DeliveryTimeSlotModalForm(
            start=start, end=end, user=user, phase=phase, job=job, single=single
        )

    context = {"form": form, "batch_users": users if len(users) > 1 else None}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot_create.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def create_scheduler_comment(request):
    """Creates a TimeSlotComment

    Args:
        request (request): Django request

    Returns:
        JsonResponse: _description_
    """
    data = {"logic_checks_feedback": ""}
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))

    users = _selected_users(request)
    resource = users[0] if users else None

    # Comments are user-owned; verify the caller may schedule each target user.
    _verify_users_schedulable(request, users)

    if request.method == "POST":
        form = CommentTimeSlotModalForm(
            request.POST, start=start, end=end, resource=resource
        )
        if form.is_valid():
            base = form.save(commit=False)

            def build_slot(u):
                return TimeSlotComment(
                    user=u,
                    comment=base.comment,
                    start=base.start,
                    end=base.end,
                )

            data = _run_batch_create(request, users, build_slot, None, None)
            _record_created(request, data)
        else:
            data = {"form_is_valid": False}
    else:
        form = CommentTimeSlotModalForm(start=start, end=end, resource=resource)

    context = {"form": form, "batch_users": users if len(users) > 1 else None}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot_comment.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def clear_scheduler_range(request):
    """Clears the range specified in the schedule. Ignore's time and focuses on day only.

    Args:
        request (request): Django request

    Returns:
        JsonResponse: _description_
    """
    data = dict()
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))
    users = _selected_users(request)
    if start is None or end is None or not users:
        return HttpResponseBadRequest()
    start = datetime_startofday(start)
    end = datetime_endofday(end)

    # Optional job/phase scope — restrict clearing to that job/phase's slots.
    job_id = clean_int(request.GET.get("job") or request.POST.get("job"))
    phase_id = clean_int(request.GET.get("phase") or request.POST.get("phase"))
    scope_phases = None
    if phase_id:
        scope_phases = Phase.objects.filter(pk=phase_id)
    elif job_id:
        scope_phases = Phase.objects.filter(job_id=job_id)

    # Verify requester can schedule for each resource's units
    for resource in users:
        resource_units = [m.unit for m in resource.unit_memberships.select_related("unit").all()]
        if resource_units and not any(
            request.user.has_perm("jobtracker.can_schedule_job", u) for u in resource_units
        ):
            raise PermissionDenied

    # Preview querysets across all selected users
    timeslots = TimeSlot.objects.filter(user__in=users, start__lt=end, end__gt=start)
    if scope_phases is not None:
        timeslots = timeslots.filter(phase__in=scope_phases)
    # Comments aren't job/phase-bound, so only clear them for an unscoped range clear
    comments = (
        TimeSlotComment.objects.filter(user__in=users, start__lt=end, end__gt=start)
        if scope_phases is None
        else TimeSlotComment.objects.none()
    )

    if request.method == "POST":
        if request.POST.get("user_action") == "approve_action":
            # Snapshot everything about to be cleared so the CLEAR action is
            # reversible and can be broadcast.
            before = [schedule_history.snapshot(s) for s in timeslots]
            if scope_phases is None:
                before += [schedule_history.snapshot_comment(c) for c in comments]
                # Per-user split-aware clear (also clears comments)
                for resource in users:
                    resource.clear_timeslots_in_range(start, end)
                    resource.clear_timeslot_comments_in_range(start, end)
            else:
                timeslots.delete()
            schedule_history.record_deletes(
                request.user, before, action_type=ScheduleActionType.CLEAR
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False

    context = {
        "start": start,
        "end": end,
        "resource": users[0] if len(users) == 1 else None,
        "users": users,
        "batch": len(users) > 1,
        "timeslots": timeslots,
        "comments": comments,
    }
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/clear_timeslot_range.html", context, request=request
    )
    return JsonResponse(data)


class _SlotDeletePermissionMixin:
    """Enforce ``can_schedule_job`` on the slot's governing unit before delete.

    The scheduler delete modals are otherwise login-only CBVs (``ChaoticaBaseView``
    is ``LoginRequiredMixin`` only), which would let any authenticated user delete
    any TimeSlot / TimeSlotComment by PK. The auth check stays with
    ``LoginRequiredMixin`` (via ``super().dispatch``); this only adds the missing
    object-level scheduling check for authenticated users."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            _verify_slot_unit_access(request, self.get_object())
        return super().dispatch(request, *args, **kwargs)


class JobSlotDeleteView(_SlotDeletePermissionMixin, ChaoticaBaseView, DeleteView):
    """View to delete a slot"""

    model = TimeSlot
    template_name = "jobtracker/modals/job_slot_delete.html"

    def form_valid(self, form):
        before = schedule_history.snapshot(self.get_object())
        response = super().form_valid(form)
        schedule_history.record_deletes(self.request.user, [before])
        # Deletes are triggered over AJAX from the schedule modal — hand back JSON
        # so the client can close the modal and refresh in place (not a redirect).
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"form_is_valid": True})
        return response

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("job_schedule", kwargs={"slug": slug})
        else:
            return reverse_lazy("view_scheduler")

    def get_context_data(self, **kwargs):
        context = super(JobSlotDeleteView, self).get_context_data(**kwargs)
        if "slug" in self.kwargs:
            context["job"] = get_object_or_404(Job, slug=self.kwargs["slug"])
        return context


class SlotCommentDeleteView(_SlotDeletePermissionMixin, ChaoticaBaseView, DeleteView):
    """View to delete a slot"""

    model = TimeSlotComment
    template_name = "jobtracker/modals/job_slot_comment_delete.html"

    def form_valid(self, form):
        before = schedule_history.snapshot_comment(self.get_object())
        response = super().form_valid(form)
        schedule_history.record_deletes(self.request.user, [before])
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"form_is_valid": True})
        return response

    def get_success_url(self):
        return reverse_lazy("view_scheduler")


class ProjectSlotDeleteView(_SlotDeletePermissionMixin, ChaoticaBaseView, DeleteView):
    """View to delete a slot"""

    model = TimeSlot
    template_name = "jobtracker/modals/project_slot_delete.html"

    def form_valid(self, form):
        before = schedule_history.snapshot(self.get_object())
        response = super().form_valid(form)
        schedule_history.record_deletes(self.request.user, [before])
        # AJAX delete from the scheduler modal — return JSON so the client closes
        # the modal in place instead of following a redirect to the project page
        # (that background GET was hanging when the origin is https on an http port).
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"form_is_valid": True})
        return response

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("project_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("view_scheduler")

    def get_context_data(self, **kwargs):
        context = super(ProjectSlotDeleteView, self).get_context_data(**kwargs)
        if "slug" in self.kwargs:
            context["project"] = get_object_or_404(Project, slug=self.kwargs["slug"])
        return context


def get_schedule_utilisation(job, phase=None):
    """Structured scoped-vs-scheduled matrix for the Utilisation widget.

    Returns {"phases": [row, ...], "grand_total": {...}|None, "hours_in_day": Decimal}
    where each row = {phase, status, confirmed, needs_attention, roles: [...],
    total: {...}, milestone: {...}}. Centralises the maths so the template can
    show scoped / scheduled / REMAINING / % + confirmed-vs-tentative + deadlines
    without per-role template tags.
    """
    from decimal import Decimal
    from datetime import datetime
    from django.utils import timezone

    phases = [phase] if phase is not None else list(job.phases.all())
    hours_in_day = phase.get_hours_in_day() if phase is not None else job.get_hours_in_day()
    today = timezone.now().date()
    required = getattr(
        TimeSlotDeliveryRole, "REQUIRED_ALLOCATIONS",
        (TimeSlotDeliveryRole.DELIVERY, TimeSlotDeliveryRole.QA),
    )

    def days(h):
        return round(h / hours_in_day, 2) if hours_in_day else Decimal(0)

    def money(h):
        return round(h, 2)

    phase_rows = []
    gt_scoped = gt_scheduled = gt_confirmed = gt_tentative = Decimal(0)

    for ph in phases:
        ph_confirmed = ph.status >= PhaseStatuses.SCHEDULED_CONFIRMED
        roles = []
        for role_id, label in TimeSlotDeliveryRole.CHOICES:
            if role_id == TimeSlotDeliveryRole.NA:
                continue
            scoped = ph.get_total_scoped_by_type(role_id)
            scheduled = ph.get_total_scheduled_by_type(role_id)
            if scoped <= 0 and scheduled <= 0:
                continue
            remaining = scoped - scheduled
            roles.append({
                "role_id": role_id, "role_name": label,
                "scoped_h": money(scoped), "scheduled_h": money(scheduled), "remaining_h": money(remaining),
                "scoped_d": days(scoped), "scheduled_d": days(scheduled), "remaining_d": days(remaining),
                "perc": ph.get_slot_type_usage_perc(role_id),
            })

        ph_scoped = ph.get_total_scoped_hours()
        ph_scheduled = ph.get_total_scheduled_hours()
        ph_conf_h = ph_scheduled if ph_confirmed else Decimal(0)
        ph_tent_h = Decimal(0) if ph_confirmed else ph_scheduled
        total = {
            "scoped_h": money(ph_scoped), "scheduled_h": money(ph_scheduled),
            "remaining_h": money(ph_scoped - ph_scheduled),
            "scoped_d": days(ph_scoped), "scheduled_d": days(ph_scheduled),
            "remaining_d": days(ph_scoped - ph_scheduled),
            "perc": ph.get_total_scheduled_perc(),
            "confirmed_h": money(ph_conf_h), "tentative_h": money(ph_tent_h),
        }

        d = ph.delivery_date
        if isinstance(d, datetime):
            d = d.date()
        milestone = {
            "delivery_date": ph.delivery_date,
            "due_to_techqa": ph.due_to_techqa,
            "due_to_presqa": ph.due_to_presqa,
            "days_to_delivery": (d - today).days if d else None,
            "is_delivery_late": ph.is_delivery_late,
        }

        needs_attention = bool(ph.is_delivery_late) or any(
            r["role_id"] in required and r["scoped_h"] > 0 and r["scheduled_h"] <= 0
            for r in roles
        )

        phase_rows.append({
            "phase": ph, "status": ph.status, "confirmed": ph_confirmed,
            "needs_attention": needs_attention, "roles": roles,
            "total": total, "milestone": milestone,
        })
        gt_scoped += ph_scoped
        gt_scheduled += ph_scheduled
        gt_confirmed += ph_conf_h
        gt_tentative += ph_tent_h

    grand_total = None
    if phase is None:
        grand_total = {
            "scoped_h": money(gt_scoped), "scheduled_h": money(gt_scheduled),
            "remaining_h": money(gt_scoped - gt_scheduled),
            "scoped_d": days(gt_scoped), "scheduled_d": days(gt_scheduled),
            "remaining_d": days(gt_scoped - gt_scheduled),
            "perc": round(100 * gt_scheduled / gt_scoped, 1) if gt_scoped > 0 else 0,
            "confirmed_h": money(gt_confirmed), "tentative_h": money(gt_tentative),
        }

    return {"phases": phase_rows, "grand_total": grand_total, "hours_in_day": hours_in_day}


def get_user_schedule_breakdown(job, phase=None):
    """Build a per-user, per-role hour breakdown for a job or phase.

    Returns a list of dicts:
        [{'user': User, 'roles': [{'role_name': str, 'hours': Decimal, 'days': Decimal}], 'total_hours': Decimal, 'total_days': Decimal}]
    """
    from decimal import Decimal

    if phase:
        slots = TimeSlot.objects.filter(phase=phase).select_related("user", "phase")
        hours_in_day = phase.get_hours_in_day()
    else:
        slots = TimeSlot.objects.filter(phase__job=job).select_related("user", "phase")
        hours_in_day = job.get_hours_in_day()

    role_names = dict(TimeSlotDeliveryRole.CHOICES)
    role_map = assigned_role_map(job, phase)   # user_pk -> [assigned role labels]

    def days(h):
        return round(h / hours_in_day, 2) if hours_in_day else Decimal(0)

    # Accumulate {user_id: {role_id: {hours, confirmed, tentative}}}
    user_data = {}
    user_objects = {}
    for slot in slots:
        uid = slot.user_id
        user_data.setdefault(uid, {})
        user_objects.setdefault(uid, slot.user)
        cell = user_data[uid].setdefault(
            slot.deliveryRole, {"hours": Decimal(0), "confirmed": Decimal(0), "tentative": Decimal(0)}
        )
        hours = slot.get_business_hours()
        cell["hours"] += hours
        if slot.is_confirmed():
            cell["confirmed"] += hours
        else:
            cell["tentative"] += hours

    result = []
    for uid, roles in user_data.items():
        user_roles = []
        total_hours = total_conf = total_tent = Decimal(0)
        for role_id, cell in sorted(roles.items()):
            if role_id == TimeSlotDeliveryRole.NA:
                continue
            total_hours += cell["hours"]
            total_conf += cell["confirmed"]
            total_tent += cell["tentative"]
            user_roles.append({
                "role_name": role_names.get(role_id, "Unknown"),
                "hours": round(cell["hours"], 2), "days": days(cell["hours"]),
                "confirmed": round(cell["confirmed"], 2),
                "tentative": round(cell["tentative"], 2),
            })
        result.append({
            "user": user_objects[uid],
            "roles": user_roles,
            "total_hours": round(total_hours, 2), "total_days": days(total_hours),
            "total_confirmed": round(total_conf, 2), "total_tentative": round(total_tent, 2),
            "assigned_roles": role_map.get(uid, []),
            "unscheduled": False,
        })

    # Assigned-but-unscheduled people (0 booked hours) so scheduling gaps show.
    missing = [pk for pk in role_map if pk not in user_data]
    for u in User.objects.filter(pk__in=missing):
        result.append({
            "user": u, "roles": [],
            "total_hours": Decimal(0), "total_days": Decimal(0),
            "total_confirmed": Decimal(0), "total_tentative": Decimal(0),
            "assigned_roles": role_map.get(u.pk, []),
            "unscheduled": True,
        })

    # Scheduled people first (alphabetical), then unscheduled assignees.
    result.sort(key=lambda x: (x["unscheduled"], str(x["user"])))
    return result


def _get_clear_queryset(job, phase, clear_type, clear_id):
    """Build the TimeSlot queryset for a clear operation."""
    if phase:
        qs = TimeSlot.objects.filter(phase=phase)
    else:
        qs = TimeSlot.objects.filter(phase__job=job)

    if clear_type == "user" and clear_id:
        qs = qs.filter(user_id=clear_id)
    elif clear_type == "role" and clear_id is not None:
        qs = qs.filter(deliveryRole=clear_id)

    return qs


def _get_clear_description(clear_type, clear_id, job, phase):
    """Build a human-readable description of what will be cleared."""
    scope = str(phase) if phase else str(job)
    if clear_type == "user" and clear_id:
        user = User.objects.filter(pk=clear_id).first()
        user_name = str(user) if user else "Unknown"
        return f"all slots for {user_name} on {scope}"
    elif clear_type == "role" and clear_id is not None:
        role_name = dict(TimeSlotDeliveryRole.CHOICES).get(clear_id, "Unknown")
        return f"all {role_name} slots on {scope}"
    else:
        return f"all slots on {scope}"


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def clear_job_schedule(request, slug):
    """Clear timeslots for a job schedule. GET returns count, POST performs deletion."""
    VALID_CLEAR_TYPES = ("all", "user", "role")
    job = get_object_or_404(Job, slug=slug)
    clear_type = request.GET.get("clear_type", "all") if request.method == "GET" else request.POST.get("clear_type", "all")
    if clear_type not in VALID_CLEAR_TYPES:
        return HttpResponseBadRequest("Invalid clear_type")
    clear_id = clean_int(request.GET.get("clear_id") if request.method == "GET" else request.POST.get("clear_id"))

    qs = _get_clear_queryset(job, None, clear_type, clear_id)

    if request.method == "POST":
        description = _get_clear_description(clear_type, clear_id, job, None)
        # Iterate + delete() per row so history/logging/phase-status recalc fire
        # (bulk .delete() bypasses them); emit one CLEAR ScheduleAction.
        slots = list(qs)
        before = [schedule_history.snapshot(s) for s in slots]
        for s in slots:
            s.delete()
        schedule_history.record_deletes(
            request.user, before, action_type=ScheduleActionType.CLEAR
        )
        count = len(before)
        logger.info("Schedule cleared by %s: %d slots — %s", request.user, count, description)
        return JsonResponse({"form_is_valid": True, "deleted": count})

    return JsonResponse({
        "count": qs.count(),
        "description": _get_clear_description(clear_type, clear_id, job, None),
    })


@job_permission_required_or_403("jobtracker.can_schedule_job", (Phase, "slug", "slug"))
def clear_phase_schedule(request, job_slug, slug):
    """Clear timeslots for a phase schedule. GET returns count, POST performs deletion."""
    VALID_CLEAR_TYPES = ("all", "user", "role")
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    clear_type = request.GET.get("clear_type", "all") if request.method == "GET" else request.POST.get("clear_type", "all")
    if clear_type not in VALID_CLEAR_TYPES:
        return HttpResponseBadRequest("Invalid clear_type")
    clear_id = clean_int(request.GET.get("clear_id") if request.method == "GET" else request.POST.get("clear_id"))

    qs = _get_clear_queryset(job, phase, clear_type, clear_id)

    if request.method == "POST":
        description = _get_clear_description(clear_type, clear_id, job, phase)
        slots = list(qs)
        before = [schedule_history.snapshot(s) for s in slots]
        for s in slots:
            s.delete()
        schedule_history.record_deletes(
            request.user, before, action_type=ScheduleActionType.CLEAR
        )
        count = len(before)
        logger.info("Schedule cleared by %s: %d slots — %s", request.user, count, description)
        return JsonResponse({"form_is_valid": True, "deleted": count})

    return JsonResponse({
        "count": qs.count(),
        "description": _get_clear_description(clear_type, clear_id, job, phase),
    })


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def move_job_schedule_slots(request, slug):
    """Move timeslots from one user to another for a job."""
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    scheduled_users = job.team_scheduled()

    unit = job.unit

    if request.method == "POST":
        form = MoveScheduleSlotsForm(request.POST, scheduled_users=scheduled_users, unit=unit, client=job.client)
        if form.is_valid():
            from_user = form.cleaned_data["from_user"]
            to_user = form.cleaned_data["to_user"]
            # Iterate + save() per row so history + logging fire (bulk .update()
            # bypasses them), and emit one MOVE ScheduleAction covering all rows.
            slots = list(TimeSlot.objects.filter(phase__job=job, user=from_user))
            before = [schedule_history.snapshot(s) for s in slots]
            for s in slots:
                s.user = to_user
                s.save()
            schedule_history.record(
                request.user, ScheduleActionType.MOVE,
                before, [schedule_history.snapshot(s) for s in slots],
            )
            count = len(slots)
            logger.info("Slots moved by %s: %d slots from %s to %s on job %s", request.user, count, from_user, to_user, job)
            data["form_is_valid"] = True
            data["moved"] = count
        else:
            data["form_is_valid"] = False
    else:
        form = MoveScheduleSlotsForm(scheduled_users=scheduled_users, unit=unit, client=job.client)

    context = {"form": form, "job": job}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/move_schedule_slots.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Phase, "slug", "slug"))
def move_phase_schedule_slots(request, job_slug, slug):
    """Move timeslots from one user to another for a phase."""
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    scheduled_users = phase.team_scheduled()

    unit = job.unit

    if request.method == "POST":
        form = MoveScheduleSlotsForm(request.POST, scheduled_users=scheduled_users, unit=unit, client=job.client)
        if form.is_valid():
            from_user = form.cleaned_data["from_user"]
            to_user = form.cleaned_data["to_user"]
            slots = list(phase.timeslots.filter(user=from_user))
            before = [schedule_history.snapshot(s) for s in slots]
            for s in slots:
                s.user = to_user
                s.save()
            schedule_history.record(
                request.user, ScheduleActionType.MOVE,
                before, [schedule_history.snapshot(s) for s in slots],
            )
            count = len(slots)
            logger.info("Slots moved by %s: %d slots from %s to %s on phase %s", request.user, count, from_user, to_user, phase)
            data["form_is_valid"] = True
            data["moved"] = count
        else:
            data["form_is_valid"] = False
    else:
        form = MoveScheduleSlotsForm(scheduled_users=scheduled_users, unit=unit, client=job.client)

    context = {"form": form, "phase": phase, "job": job}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/move_schedule_slots.html", context, request=request
    )
    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Schedule management tools (shift / swap / onsite) — shared job & phase logic
# ---------------------------------------------------------------------------

def _base_slot_qs(job, phase):
    """Delivery-schedule timeslots for a job or a single phase."""
    if phase is not None:
        return phase.timeslots.all()
    return TimeSlot.objects.filter(phase__job=job)


def _refresh_phase_dates(phase_ids):
    """Re-derive stored phase dates after a bulk slot change."""
    for ph in Phase.objects.filter(pk__in=[p for p in phase_ids if p]):
        ph.save()


def _handle_shift(request, job, phase, template):
    from django.db.models import F
    from datetime import timedelta
    from django.utils import timezone

    data = {}
    base = _base_slot_qs(job, phase)
    if request.method == "POST":
        form = ScheduleShiftForm(request.POST)
        if form.is_valid():
            qs = base
            if form.cleaned_data["only_future"]:
                qs = qs.filter(start__date__gte=timezone.now().date())
            delta = timedelta(days=form.signed_days())
            affected = list(qs.values_list("phase_id", flat=True).distinct())
            affected_pks = list(qs.values_list("pk", flat=True))
            before = [schedule_history.snapshot(s) for s in TimeSlot.objects.filter(pk__in=affected_pks)]
            count = qs.update(start=F("start") + delta, end=F("end") + delta)
            _refresh_phase_dates(affected)
            schedule_history.record(
                request.user, ScheduleActionType.MOVE,
                before, [schedule_history.snapshot(s) for s in TimeSlot.objects.filter(pk__in=affected_pks)],
            )
            n = form.signed_days()
            logger.info(
                "Schedule shifted by %s: %d slots %+d days on %s",
                request.user, count, n, phase or job,
            )
            when = "later" if n > 0 else "earlier"
            data["form_is_valid"] = True
            data["message"] = "{} timeslot{} shifted {} day{} {}.".format(
                count, "" if count == 1 else "s", abs(n),
                "" if abs(n) == 1 else "s", when,
            )
        else:
            data["form_is_valid"] = False
    else:
        form = ScheduleShiftForm()

    context = {"form": form, "job": job, "phase": phase}
    data["html_form"] = loader.render_to_string(template, context, request=request)
    return JsonResponse(data)


def _handle_swap(request, job, phase, scheduled_users, template):
    data = {}
    base = _base_slot_qs(job, phase)
    if request.method == "POST":
        form = ScheduleSwapForm(request.POST, scheduled_users=scheduled_users)
        if form.is_valid():
            a = form.cleaned_data["user_a"]
            b = form.cleaned_data["user_b"]
            a_ids = list(base.filter(user=a).values_list("pk", flat=True))
            b_ids = list(base.filter(user=b).values_list("pk", flat=True))
            all_ids = a_ids + b_ids
            before = [schedule_history.snapshot(s) for s in TimeSlot.objects.filter(pk__in=all_ids)]
            TimeSlot.objects.filter(pk__in=a_ids).update(user=b)
            TimeSlot.objects.filter(pk__in=b_ids).update(user=a)
            schedule_history.record(
                request.user, ScheduleActionType.MOVE,
                before, [schedule_history.snapshot(s) for s in TimeSlot.objects.filter(pk__in=all_ids)],
            )
            logger.info(
                "Schedule swap by %s: %s (%d) <-> %s (%d) on %s",
                request.user, a, len(a_ids), b, len(b_ids), phase or job,
            )
            data["form_is_valid"] = True
            data["message"] = "Swapped {} and {} timeslots between {} and {}.".format(
                len(a_ids), len(b_ids), a.get_full_name(), b.get_full_name()
            )
        else:
            data["form_is_valid"] = False
    else:
        form = ScheduleSwapForm(scheduled_users=scheduled_users)

    context = {"form": form, "job": job, "phase": phase}
    data["html_form"] = loader.render_to_string(template, context, request=request)
    return JsonResponse(data)


def _handle_onsite(request, job, phase, scheduled_users, template):
    data = {}
    base = _base_slot_qs(job, phase).filter(
        deliveryRole=TimeSlotDeliveryRole.DELIVERY
    )
    if request.method == "POST":
        form = ScheduleOnsiteForm(request.POST, scheduled_users=scheduled_users)
        if form.is_valid():
            onsite = form.cleaned_data["location"] == "onsite"
            qs = base
            target_user = form.cleaned_data.get("user")
            if target_user:
                qs = qs.filter(user=target_user)
            affected_pks = list(qs.values_list("pk", flat=True))
            before = [schedule_history.snapshot(s) for s in TimeSlot.objects.filter(pk__in=affected_pks)]
            count = qs.update(is_onsite=onsite)
            schedule_history.record(
                request.user, ScheduleActionType.UPDATE,
                before, [schedule_history.snapshot(s) for s in TimeSlot.objects.filter(pk__in=affected_pks)],
            )
            logger.info(
                "Schedule onsite=%s by %s: %d slots on %s",
                onsite, request.user, count, phase or job,
            )
            data["form_is_valid"] = True
            data["message"] = "{} delivery timeslot{} set as {}.".format(
                count, "" if count == 1 else "s", "onsite" if onsite else "remote"
            )
        else:
            data["form_is_valid"] = False
    else:
        form = ScheduleOnsiteForm(scheduled_users=scheduled_users)

    context = {"form": form, "job": job, "phase": phase}
    data["html_form"] = loader.render_to_string(template, context, request=request)
    return JsonResponse(data)


_SHIFT_TMPL = "jobtracker/modals/schedule_shift.html"
_SWAP_TMPL = "jobtracker/modals/schedule_swap.html"
_ONSITE_TMPL = "jobtracker/modals/schedule_onsite.html"


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def shift_job_schedule(request, slug):
    job = get_object_or_404(Job, slug=slug)
    return _handle_shift(request, job, None, _SHIFT_TMPL)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Phase, "slug", "slug"))
def shift_phase_schedule(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    return _handle_shift(request, job, phase, _SHIFT_TMPL)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def swap_job_schedule(request, slug):
    job = get_object_or_404(Job, slug=slug)
    return _handle_swap(request, job, None, job.team_scheduled(), _SWAP_TMPL)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Phase, "slug", "slug"))
def swap_phase_schedule(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    return _handle_swap(request, job, phase, phase.team_scheduled(), _SWAP_TMPL)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def onsite_job_schedule(request, slug):
    job = get_object_or_404(Job, slug=slug)
    return _handle_onsite(request, job, None, job.team_scheduled(), _ONSITE_TMPL)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Phase, "slug", "slug"))
def onsite_phase_schedule(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    return _handle_onsite(request, job, phase, phase.team_scheduled(), _ONSITE_TMPL)
