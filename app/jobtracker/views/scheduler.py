from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.template import loader
from django.db.models import Q, Prefetch
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import page_defaults
from chaotica_utils.views import ChaoticaBaseView
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
)
from ..enums import UserSkillRatings, TimeSlotDeliveryRole
from ..utils import get_scheduler_slots, get_scheduler_members
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
import time
from constance import config


logger = logging.getLogger(__name__)


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


@login_required
def view_scheduler(request):
    context = {}
    template = loader.get_template("scheduler.html")
    context = {**context, **page_defaults(request)}
    context["filter_form"] = SchedulerFilter(request.GET)
    return HttpResponse(template.render(context, request))


@login_required
def view_scheduler_slots(request):
    return get_scheduler_slots(request)


@login_required
def view_scheduler_members(request):
    return get_scheduler_members(request)


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
    data = dict()
    if request.method == "POST":
        form = ChangeTimeSlotCommentDateModalForm(request.POST, instance=slot)
        if form.is_valid():
            form.save()
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
    data = dict()
    if request.method == "POST":
        form = CommentTimeSlotModalForm(request.POST, instance=slot)

        if form.is_valid():
            form.save()
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
    data = dict()
    if request.method == "POST":
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
            updated_slot.save()
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
    data = dict()

    if request.method == "POST":
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
            updated_slot.save()
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


@unit_permission_required_or_403("jobtracker.can_schedule_job")
def create_scheduler_internal_slot(request):
    """Creates an Internal type of TimeSlot

    Args:
        request (request): Django request

    Returns:
        JsonResponse: _description_
    """
    data = dict()
    # start = clean_datetime(request.GET.get("start", None))
    # end = clean_datetime(request.GET.get("end", None))

    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))

    resource_id = clean_int(request.GET.get("resource_id", None))
    if resource_id:
        resource = get_object_or_404(User, pk=resource_id)

    if request.method == "POST":
        form = NonDeliveryTimeSlotModalForm(
            request.POST, start=start, end=end, resource=resource
        )
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = NonDeliveryTimeSlotModalForm(start=start, end=end, resource=resource)

    context = {"form": form}
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
    data = dict()
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))
    resource_id = clean_int(request.GET.get("resource_id", None))
    project_id = clean_int(request.GET.get("project", None))

    if resource_id:
        user = get_object_or_404(User, pk=resource_id)
    else:
        user = None

    if project_id:
        project = get_object_or_404(Project, pk=project_id)
    else:
        project = None

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
            slot = form.save(commit=False)
            slots = slot.overlapping_slots()
            if slots and not force:
                # Check if any of these are unavailable
                if slots.filter(slot_type__is_working=False).exists():
                    # Unavailable
                    unavailable_slots = slots.filter(slot_type__is_working=False)
                    # Overlapping slots!
                    data["form_is_valid"] = False
                    data["logic_checks_failed"] = True
                    data["logic_checks_can_bypass"] = False
                    data["logic_checks_feedback"] += loader.render_to_string(
                        "partials/scheduler/logicchecks/unavailable.html",
                        {"slot": slot, "unavailable_slots": unavailable_slots},
                        request=request,
                    )
                else:
                    # Overlapping slots!
                    data["form_is_valid"] = False
                    data["logic_checks_failed"] = True
                    data["logic_checks_can_bypass"] = True
                    data["logic_checks_feedback"] = loader.render_to_string(
                        "partials/scheduler/logicchecks/overlaps.html",
                        {"slot": slot, "overlapping_slots": slots},
                        request=request,
                    )
            else:
                slot.save()
                data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = ProjectTimeSlotModalForm(
            start=start,
            end=end,
            user=user,
            project=project,
        )

    context = {"form": form}
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
    data = dict()
    data["logic_checks_feedback"] = ""
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))
    resource_id = clean_int(request.GET.get("resource_id", None))
    job_id = clean_int(request.GET.get("job", None))
    phase_id = clean_int(request.GET.get("phase", None))

    if resource_id:
        user = get_object_or_404(User, pk=resource_id)
    else:
        user = None

    if job_id:
        job = get_object_or_404(Job, pk=job_id)
        if phase_id:
            phase = get_object_or_404(Phase, pk=phase_id)
        else:
            phase = None
    else:
        job = None
        phase = None

    if request.method == "POST":
        force = request.POST.get("force", None)
        form = DeliveryTimeSlotModalForm(
            request.POST, start=start, end=end, user=user, phase=phase, job=job
        )
        if form.is_valid():
            slot = form.save(commit=False)
            slots = slot.overlapping_slots()
            data["logic_checks_failed"] = False

            # Non-bypassable: framework closed check
            framework = slot.phase.job.associated_framework
            if framework and framework.closed:
                data["form_is_valid"] = False
                data["logic_checks_failed"] = True
                data["logic_checks_can_bypass"] = False
                data["logic_checks_feedback"] = loader.render_to_string(
                    "partials/scheduler/logicchecks/framework_closed.html",
                    {"framework": framework},
                    request=request,
                )

            # Non-bypassable: framework over-allocation check
            if (
                not data["logic_checks_failed"]
                and framework
                and not framework.allow_over_allocation
            ):
                slot_hours = slot.get_business_hours()
                hours_in_day = framework.get_hours_in_day()
                slot_days = round(slot_hours / hours_in_day, 1) if hours_in_day else 0
                days_allocated = framework.days_allocated()
                new_total = days_allocated + slot_days
                if new_total > framework.total_days:
                    data["form_is_valid"] = False
                    data["logic_checks_failed"] = True
                    data["logic_checks_can_bypass"] = False
                    data["logic_checks_feedback"] = loader.render_to_string(
                        "partials/scheduler/logicchecks/framework_over_allocated.html",
                        {
                            "framework": framework,
                            "days_allocated": days_allocated,
                            "slot_days": slot_days,
                            "new_total": new_total,
                        },
                        request=request,
                    )

            # Non-bypassable: onboarding required check
            if not data["logic_checks_failed"] and (
                slot.phase.job.client.onboarding_required
                and not slot.phase.job.client.onboarded_users.filter(
                    user=user, client=slot.phase.job.client
                ).exists()
            ):
                data["form_is_valid"] = False
                data["logic_checks_failed"] = True
                data["logic_checks_can_bypass"] = False
                data["logic_checks_feedback"] = loader.render_to_string(
                    "partials/scheduler/logicchecks/not_onboarded.html",
                    {"slot": slot, "phase": slot.phase},
                    request=request,
                )

            if not data["logic_checks_failed"]:
                if not force:
                    # These logic checks can be bypassed

                    # Bypassable: phase over-scoped warning
                    _scoped_data = _check_phase_scoped(slot, request)
                    if _scoped_data:
                        data["form_is_valid"] = False
                        data["logic_checks_failed"] = True
                        data["logic_checks_can_bypass"] = True
                        data["logic_checks_feedback"] += _scoped_data["logic_checks_feedback"]

                    # Bypassable: framework over-budget warning (allows over-allocation)
                    if (
                        framework
                        and framework.allow_over_allocation
                    ):
                        slot_hours = slot.get_business_hours()
                        hours_in_day = framework.get_hours_in_day()
                        slot_days = round(slot_hours / hours_in_day, 1) if hours_in_day else 0
                        days_allocated = framework.days_allocated()
                        new_total = days_allocated + slot_days
                        if new_total > framework.total_days:
                            data["form_is_valid"] = False
                            data["logic_checks_failed"] = True
                            data["logic_checks_can_bypass"] = True
                            data["logic_checks_feedback"] += loader.render_to_string(
                                "partials/scheduler/logicchecks/framework_over_budget_warning.html",
                                {
                                    "framework": framework,
                                    "days_allocated": days_allocated,
                                    "slot_days": slot_days,
                                    "new_total": new_total,
                                },
                                request=request,
                            )

                    if slots:
                        # Check if any of these are unavailable
                        if slots.filter(slot_type__is_working=False).exists():
                            # Unavailable
                            unavailable_slots = slots.filter(slot_type__is_working=False)
                            # Overlapping slots!
                            data["form_is_valid"] = False
                            data["logic_checks_failed"] = True
                            data["logic_checks_can_bypass"] = False
                            data["logic_checks_feedback"] += loader.render_to_string(
                                "partials/scheduler/logicchecks/unavailable.html",
                                {"slot": slot, "unavailable_slots": unavailable_slots},
                                request=request,
                            )
                        else:
                            # Overlapping slots!
                            data["form_is_valid"] = False
                            data["logic_checks_failed"] = True
                            data["logic_checks_can_bypass"] = True
                            data["logic_checks_feedback"] += loader.render_to_string(
                                "partials/scheduler/logicchecks/overlaps.html",
                                {"slot": slot, "overlapping_slots": slots},
                                request=request,
                            )

                    if (
                        slot.phase.job.client.onboarding_required
                        and slot.phase.job.client.onboarded_users.filter(
                            user=user
                        ).exists()
                    ):
                        onboarding = slot.phase.job.client.onboarded_users.filter(
                            user=user
                        ).first()
                        if onboarding.is_stale:
                            data["form_is_valid"] = False
                            data["logic_checks_failed"] = True
                            data["logic_checks_can_bypass"] = True
                            data["logic_checks_feedback"] += loader.render_to_string(
                                "partials/scheduler/logicchecks/stale_onboarding.html",
                                {"slot": slot, "phase": phase},
                                request=request,
                            )

                if not data["logic_checks_failed"] or (
                    data["logic_checks_failed"] and force
                ):
                    slot.save()
                    data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = DeliveryTimeSlotModalForm(
            start=start, end=end, user=user, phase=phase, job=job
        )

    context = {"form": form}
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
    data = dict()
    start = clean_datetime(request.GET.get("start", None))
    end = clean_datetime(request.GET.get("end", None))
    resource_id = clean_int(request.GET.get("resource_id", None))
    if resource_id:
        resource = get_object_or_404(User, pk=resource_id)

    if request.method == "POST":
        form = CommentTimeSlotModalForm(
            request.POST, start=start, end=end, resource=resource
        )
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = CommentTimeSlotModalForm(start=start, end=end, resource=resource)

    context = {"form": form}
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
    resource_id = clean_int(request.GET.get("resource_id", None))
    if start is None or end is None or resource_id is None:
        return HttpResponseBadRequest()
    start = datetime_startofday(start)
    end = datetime_endofday(end)

    resource = get_object_or_404(User, pk=resource_id)
    timeslots = resource.get_timeslots_objs(start, end)
    comments = resource.get_timeslot_comments_objs(start, end)

    if request.method == "POST":
        if request.POST.get("user_action") == "approve_action":
            # Ok, user has confirmed. Lets do it!
            resource.clear_timeslots_in_range(start, end)
            resource.clear_timeslot_comments_in_range(start, end)
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False

    context = {"start": start, "end": end, "resource": resource, "timeslots": timeslots, "comments": comments}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/clear_timeslot_range.html", context, request=request
    )
    return JsonResponse(data)


class JobSlotDeleteView(ChaoticaBaseView, DeleteView):
    """View to delete a slot"""

    model = TimeSlot
    template_name = "jobtracker/modals/job_slot_delete.html"

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


class SlotCommentDeleteView(ChaoticaBaseView, DeleteView):
    """View to delete a slot"""

    model = TimeSlotComment
    template_name = "jobtracker/modals/job_slot_comment_delete.html"

    def get_success_url(self):
        return reverse_lazy("view_scheduler")


class ProjectSlotDeleteView(ChaoticaBaseView, DeleteView):
    """View to delete a slot"""

    model = TimeSlot
    template_name = "jobtracker/modals/project_slot_delete.html"

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


def get_user_schedule_breakdown(job, phase=None):
    """Build a per-user, per-role hour breakdown for a job or phase.

    Returns a list of dicts:
        [{'user': User, 'roles': [{'role_name': str, 'hours': Decimal, 'days': Decimal}], 'total_hours': Decimal, 'total_days': Decimal}]
    """
    from decimal import Decimal

    if phase:
        slots = TimeSlot.objects.filter(phase=phase).select_related("user")
        hours_in_day = phase.get_hours_in_day()
    else:
        slots = TimeSlot.objects.filter(phase__job=job).select_related("user")
        hours_in_day = job.get_hours_in_day()

    role_names = dict(TimeSlotDeliveryRole.CHOICES)

    # Accumulate {user_id: {role_id: hours}}
    user_data = {}
    user_objects = {}
    for slot in slots:
        uid = slot.user_id
        if uid not in user_data:
            user_data[uid] = {}
            user_objects[uid] = slot.user
        role_id = slot.deliveryRole
        hours = slot.get_business_hours()
        user_data[uid][role_id] = user_data[uid].get(role_id, Decimal(0)) + hours

    result = []
    for uid, roles in user_data.items():
        user_roles = []
        total_hours = Decimal(0)
        for role_id, hours in sorted(roles.items()):
            if role_id == TimeSlotDeliveryRole.NA:
                continue
            total_hours += hours
            days = round(hours / hours_in_day, 2) if hours_in_day else Decimal(0)
            user_roles.append({
                "role_name": role_names.get(role_id, "Unknown"),
                "hours": round(hours, 2),
                "days": days,
            })
        total_days = round(total_hours / hours_in_day, 2) if hours_in_day else Decimal(0)
        result.append({
            "user": user_objects[uid],
            "roles": user_roles,
            "total_hours": round(total_hours, 2),
            "total_days": total_days,
        })

    result.sort(key=lambda x: str(x["user"]))
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
    job = get_object_or_404(Job, slug=slug)
    clear_type = request.GET.get("clear_type", "all") if request.method == "GET" else request.POST.get("clear_type", "all")
    clear_id = clean_int(request.GET.get("clear_id") if request.method == "GET" else request.POST.get("clear_id"))

    qs = _get_clear_queryset(job, None, clear_type, clear_id)

    if request.method == "POST":
        count = qs.count()
        qs.delete()
        return JsonResponse({"form_is_valid": True, "deleted": count})

    return JsonResponse({
        "count": qs.count(),
        "description": _get_clear_description(clear_type, clear_id, job, None),
    })


@job_permission_required_or_403("jobtracker.can_schedule_job", (Phase, "slug", "slug"))
def clear_phase_schedule(request, job_slug, slug):
    """Clear timeslots for a phase schedule. GET returns count, POST performs deletion."""
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    clear_type = request.GET.get("clear_type", "all") if request.method == "GET" else request.POST.get("clear_type", "all")
    clear_id = clean_int(request.GET.get("clear_id") if request.method == "GET" else request.POST.get("clear_id"))

    qs = _get_clear_queryset(job, phase, clear_type, clear_id)

    if request.method == "POST":
        count = qs.count()
        qs.delete()
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

    if request.method == "POST":
        form = MoveScheduleSlotsForm(request.POST, scheduled_users=scheduled_users)
        if form.is_valid():
            from_user = form.cleaned_data["from_user"]
            to_user = form.cleaned_data["to_user"]
            count = TimeSlot.objects.filter(phase__job=job, user=from_user).update(user=to_user)
            data["form_is_valid"] = True
            data["moved"] = count
        else:
            data["form_is_valid"] = False
    else:
        form = MoveScheduleSlotsForm(scheduled_users=scheduled_users)

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

    if request.method == "POST":
        form = MoveScheduleSlotsForm(request.POST, scheduled_users=scheduled_users)
        if form.is_valid():
            from_user = form.cleaned_data["from_user"]
            to_user = form.cleaned_data["to_user"]
            count = phase.timeslots.filter(user=from_user).update(user=to_user)
            data["form_is_valid"] = True
            data["moved"] = count
        else:
            data["form_is_valid"] = False
    else:
        form = MoveScheduleSlotsForm(scheduled_users=scheduled_users)

    context = {"form": form, "phase": phase, "job": job}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/move_schedule_slots.html", context, request=request
    )
    return JsonResponse(data)
