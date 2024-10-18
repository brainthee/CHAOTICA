from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.template import loader
from django.db.models import Q
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
from ..decorators import unit_permission_required_or_403
from ..forms import (
    NonDeliveryTimeSlotModalForm,
    SchedulerFilter,
    ChangeTimeSlotDateModalForm,
    DeliveryTimeSlotModalForm,
    ProjectTimeSlotModalForm,
    CommentTimeSlotModalForm,
    ChangeTimeSlotCommentDateModalForm,
)
from ..enums import UserSkillRatings
import logging
from django.contrib.auth.decorators import login_required
from chaotica_utils.utils import (
    clean_int,
    clean_datetime,
    clean_fullcalendar_datetime,
    datetime_startofday,
    datetime_endofday,
)
from django.contrib import messages


logger = logging.getLogger(__name__)


@login_required
def view_scheduler(request):
    context = {}
    template = loader.get_template("scheduler.html")
    context = {**context, **page_defaults(request)}
    context["filter_form"] = SchedulerFilter(request.GET)
    return HttpResponse(template.render(context, request))


def _filter_users_on_query(request):
    query = Q()
    filter_form = SchedulerFilter(request.GET)
    if filter_form.is_valid():
        show_inactive_users = filter_form.cleaned_data.get("show_inactive_users")
    else:
        show_inactive_users = False
        
    cleaned_data = filter_form.clean()

    # Starting users filter
    users_pk = []
    # This pre-loads which users we can see the schedule of.
    # It's actually not ideal because if we view a job/phase,
    # but say we don't have permission to see the schedule of someone - we can't see a complete schedule for that job
    for org_unit in get_objects_for_user(
        request.user, "jobtracker.view_users_schedule"
    ):
        for user in org_unit.get_allMembers():
            if user.pk not in users_pk:
                users_pk.append(user.pk)

    if filter_form.is_valid():
        # If we're passed a job/phase ID - filter on that.
        jobs = cleaned_data.get("jobs")
        if jobs:
            for job in jobs:
                query.add(Q(pk__in=job.team()), Q.AND)

        phases = cleaned_data.get("phases")
        if phases:
            for phase in phases:
                query.add(Q(pk__in=phase.team()), Q.AND)
        
        if not jobs and not phases:
            query.add(Q(pk__in=users_pk), Q.AND)

        # Now lets apply the filters from the query...
        ## Filter users
        if not show_inactive_users:
            query.add(Q(is_active=True), Q.AND)

        users_q = cleaned_data.get("users")
        if users_q:
            query.add(Q(pk__in=users_q), Q.AND)

        ## Filter org unit
        org_units = cleaned_data.get("org_units")
        org_unit_roles = cleaned_data.get("org_unit_roles")

        if org_units:
            query.add(
                Q(
                    unit_memberships__in=OrganisationalUnitMember.objects.filter(
                        unit__in=org_units,
                        roles__in=(
                            org_unit_roles
                            if org_unit_roles
                            else OrganisationalUnitRole.objects.all()
                        ),
                    )
                ),
                Q.AND,
            )
        else:
            if org_unit_roles:
                query.add(
                    Q(
                        unit_memberships__in=OrganisationalUnitMember.objects.filter(
                            roles__in=org_unit_roles,
                        )
                    ),
                    Q.AND,
                )

        ## Filter on skills
        skills_specialist = cleaned_data.get("skills_specialist")
        if skills_specialist:
            query.add(
                Q(
                    skills__in=UserSkill.objects.filter(
                        skill__in=skills_specialist, rating=UserSkillRatings.SPECIALIST
                    )
                ),
                Q.AND,
            )

        skills_can_do_alone = cleaned_data.get("skills_can_do_alone")
        if skills_can_do_alone:
            query.add(
                Q(
                    skills__in=UserSkill.objects.filter(
                        skill__in=skills_can_do_alone,
                        rating=UserSkillRatings.CAN_DO_ALONE,
                    )
                ),
                Q.AND,
            )

        skills_can_do_support = cleaned_data.get("skills_can_do_support")
        if skills_can_do_support:
            query.add(
                Q(
                    skills__in=UserSkill.objects.filter(
                        skill__in=skills_can_do_support,
                        rating=UserSkillRatings.CAN_DO_WITH_SUPPORT,
                    )
                ),
                Q.AND,
            )

        # Filter on service
        # This is a bit mind bending. Of the service(s) selected, each will have some desired/needed skills
        # We then need to select the users based off containing a skill in either desired or needed..
        services = cleaned_data.get("services")
        for service in services:
            query.add(Q(pk__in=service.users_can_conduct()), Q.AND)

    extra_users = cleaned_data.get("include_user")
    if extra_users:
        query.add(
            Q(
                pk__in=extra_users
            ),
            Q.OR,
        )

    return User.objects.filter(query).distinct().order_by("last_name", "first_name").prefetch_related("timeslots")


@login_required
def view_scheduler_slots(request):
    data = []
    filtered_users = _filter_users_on_query(request)
    phase_focus = None

    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    job_id = clean_int(request.GET.get("job", None))
    phase_id = clean_int(request.GET.get("phase", None))

    if phase_id:
        phase_focus = get_object_or_404(Phase, pk=phase_id)
    elif job_id:
        job = get_object_or_404(Job, pk=job_id)
        phase_focus = job
    
    # # Lets get slots!
    # slots = TimeSlot.objects.filter(user__in=filtered_users, end__gte=start, start__lte=end)
    # print("got slots")
    # for slot in slots:
    #     print("processing "+str(slot))
    #     slot_json = slot.get_schedule_json()
    #     is_focused = False
    #     if phase_focus:
    #         if slot.phase:
    #             if slot.phase == phase_focus:
    #                 is_focused = True
    #             if not is_focused and slot.phase.job == phase_focus:
    #                 is_focused = True
    #     if phase_focus and not is_focused:
    #         slot_json["display"] = "background"
    #     data.append(slot_json)
    #     print("done processing "+str(slot))

    for user in filtered_users:
        data = data + user.get_timeslots(start=start, end=end, phase_focus=phase_focus)
        data = data + user.get_timeslot_comments(start=start, end=end)
        data = data + user.get_holidays(
            start=start,
            end=end,
        )
    return JsonResponse(data, safe=False)


@login_required
def view_scheduler_members(request):
    data = []
    filtered_users = _filter_users_on_query(request)
    for user in filtered_users:
        user_title = str(user)
        main_org = user.unit_memberships.first()
        data.append(
            {
                "id": user.pk,
                "title": user_title,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "url": user.get_absolute_url(),
                "html_view": user.get_table_display_html(),
                "businessHours": (
                    {
                        "startTime": main_org.unit.businessHours_startTime,
                        "endTime": main_org.unit.businessHours_endTime,
                        "daysOfWeek": main_org.unit.businessHours_days,
                    }
                    if main_org
                    else {
                        "startTime": "",
                        "endTime": "",
                        "daysOfWeek": "",
                    }
                ),
                "workingHours": (
                    {
                        "startTime": main_org.unit.businessHours_startTime,
                        "endTime": main_org.unit.businessHours_endTime,
                        "daysOfWeek": main_org.unit.businessHours_days,
                    }
                    if main_org
                    else {
                        "startTime": "",
                        "endTime": "",
                        "daysOfWeek": "",
                    }
                ),
            }
        )
    return JsonResponse(data, safe=False)


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
        form = ChangeTimeSlotDateModalForm(request.POST, instance=slot)
        if form.is_valid():
            form.save()
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
        if slot.is_delivery():
            form = DeliveryTimeSlotModalForm(request.POST, instance=slot)
        elif slot.is_project():
            form = ProjectTimeSlotModalForm(request.POST, instance=slot)
        else:
            form = NonDeliveryTimeSlotModalForm(request.POST, instance=slot)

        if form.is_valid():
            form.save()
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
            if slots and not force:
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

    if request.method == "POST":
        if request.POST.get("user_action") == "approve_action":
            # Ok, user has confirmed. Lets do it!
            resource.clear_timeslots_in_range(start, end)
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False

    context = {"start": start, "end": end, "resource": resource, "timeslots": timeslots}
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
