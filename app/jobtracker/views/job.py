from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.http import (
    HttpResponseRedirect,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.template import loader
from django.db.models import Q
from django.contrib.auth.mixins import UserPassesTestMixin
from guardian.shortcuts import get_objects_for_user
from ..decorators import unit_permission_required_or_403, job_permission_required_or_403
from ..mixins import UnitPermissionRequiredMixin, JobPermissionRequiredMixin
from django.views import View
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from dal import autocomplete
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from chaotica_utils.enums import UnitRoles
from ..models import (
    Job,
    JobSupportTeamRole,
    BillingCode,
    TimeSlot,
    TimeSlotType,
    OrganisationalUnit,
    WorkflowTask,
    Contact,
)
from ..forms import (
    ScopeInlineForm,
    DeliveryTimeSlotModalForm,
    AddNote,
    JobForm,
    AssignUserField,
    ScopeForm,
    AssignJobFramework,
    AssignJobBillingCode,
    JobSupportTeamRoleForm,
)
from ..enums import JobStatuses, TimeSlotDeliveryRole, DefaultTimeSlotTypes
from .helpers import _process_assign_user, _process_assign_contact
import logging


logger = logging.getLogger(__name__)

# TODO: setup events for schedule so it comes back with member's only

# TODO: Permissions for jobs needs revisiting. TLDR; deal with non unit members
# by adding them permissions directly to the job


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_gantt_data(request, slug):
    job = get_object_or_404(Job, slug=slug)
    return JsonResponse(job.get_gantt_json(), safe=False)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_slots(request, slug):
    data = []
    job = get_object_or_404(Job, slug=slug)
    slots = TimeSlot.objects.filter(phase__job=job)
    for slot in slots:
        data.append(
            slot.get_schedule_json(
                url=reverse(
                    "change_job_schedule_slot", kwargs={"slug": job.slug, "pk": slot.pk}
                )
            )
        )
    return JsonResponse(data, safe=False)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_members(request, slug):
    data = []
    job = get_object_or_404(Job, slug=slug)
    scheduled_users = job.team_scheduled()
    if scheduled_users:
        for user in scheduled_users:
            data.append(
                {
                    "id": user.pk,
                    "title": str(user),
                    "businessHours": {
                        "startTime": job.unit.businessHours_startTime,
                        "endTime": job.unit.businessHours_endTime,
                        "daysOfWeek": job.unit.businessHours_days,
                    },
                }
            )
    return JsonResponse(data, safe=False)


@job_permission_required_or_403(
    "jobtracker.can_manage_framework_job", (Job, "slug", "slug")
)
def assign_job_framework(request, slug):
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    if request.method == "POST":
        form = AssignJobFramework(request.POST, instance=job)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = AssignJobFramework(instance=job)

    context = {
        "form": form,
        "job": job,
    }
    data["html_form"] = loader.render_to_string(
        "modals/assign_job_framework.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.assign_billingcodes", (Job, "slug", "slug"))
def assign_job_billingcodes(request, slug):
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    if request.method == "POST":
        form = AssignJobBillingCode(request.POST, instance=job)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = AssignJobBillingCode(instance=job)

    context = {
        "form": form,
        "job": job,
    }
    data["html_form"] = loader.render_to_string(
        "modals/assign_job_billingcodes.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_assign_poc_job", (Job, "slug", "slug"))
def assign_job_poc(request, slug):
    job = get_object_or_404(Job, slug=slug)
    contacts = Contact.objects.filter(company=job.client)
    return _process_assign_contact(
        request, job, "primary_client_poc", contacts=contacts
    )


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "slug"))
def assign_job_field(request, slug, field):
    valid_fields = [
        "account_manager",
        "dep_account_manager",
        "scoped_by",
        "scoped_signed_off_by",
    ]
    job = get_object_or_404(Job, slug=slug)
    if field in valid_fields:
        if field == "scoped_by":
            return _process_assign_user(request, job, field, multiple=True)
        else:
            return _process_assign_user(request, job, field)
    else:
        return HttpResponseBadRequest()


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "slug"))
def assign_job_scoped(request, slug):
    job = get_object_or_404(Job, slug=slug)
    return _process_assign_user(request, job, "scoped_by", multiple=True)


@job_permission_required_or_403("jobtracker.can_scope_jobs", (Job, "slug", "slug"))
def job_edit_scope(request, slug):
    is_ajax = False
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        is_ajax = True

    job = get_object_or_404(Job, slug=slug)
    data = {}
    data["form_is_valid"] = False
    if request.method == "POST":
        form = ScopeInlineForm(request.POST, instance=job)
        if form.is_valid():
            job = form.save()
            # add activity logs
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
            log_system_activity(
                job, "Scope edited (" + ", ".join(form.changed_data) + ")"
            )
            if not is_ajax:
                return HttpResponseRedirect(
                    reverse("job_detail", kwargs={"slug": slug})
                )
    else:
        form = ScopeInlineForm(instance=job)

    context = {"scopeInlineForm": form, "job": job}
    data["html_form"] = loader.render_to_string(
        "partials/job/forms/scope.html", context, request=request
    )

    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def change_job_schedule_slot(request, slug, pk=None):
    job = get_object_or_404(Job, slug=slug)
    slot = None
    if pk:
        slot = get_object_or_404(TimeSlot, pk=pk, phase__job=job)
    data = dict()
    if request.method == "POST":
        form = DeliveryTimeSlotModalForm(request.POST, instance=slot, slug=slug)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.slot_type = TimeSlotType.get_builtin_object(
                DefaultTimeSlotTypes.DELIVERY
            )
            slot.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = DeliveryTimeSlotModalForm(instance=slot, slug=slug)

    context = {"form": form, "job": job}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_slot.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def job_support_team_add(request, slug):
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    if request.method == "POST":
        form = JobSupportTeamRoleForm(request.POST)
        if form.is_valid():
            role = form.save(commit=False)
            role.job = job
            role.save()
            log_system_activity(
                job,
                "{user} added with {hrs}hrs as {role} support role.".format(
                    user=role.user,
                    hrs=str(role.allocated_hours),
                    role=role.get_role_display(),
                ),
                author=request.user,
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = JobSupportTeamRoleForm()

    context = {"form": form, "job": job}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_support_team_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def job_support_team_edit(request, slug, pk):
    job = get_object_or_404(Job, slug=slug)
    support_role = get_object_or_404(JobSupportTeamRole, pk=pk, job=job)
    data = dict()
    if request.method == "POST":
        form = JobSupportTeamRoleForm(request.POST, instance=support_role)
        if form.is_valid():
            role = form.save()
            log_system_activity(
                job,
                "{user} updated with {hrs}hrs as {role} support role.".format(
                    user=role.user,
                    hrs=str(role.allocated_hours),
                    role=role.get_role_display(),
                ),
                author=request.user,
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = JobSupportTeamRoleForm(instance=support_role)

    context = {"form": form, "job": job}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_support_team_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def job_support_team_mark_used(request, slug, pk):
    job = get_object_or_404(Job, slug=slug)
    support_role = get_object_or_404(JobSupportTeamRole, pk=pk, job=job)
    data = dict()
    if request.method == "POST":
        if request.POST.get("user_action") == "approve_action":
            support_role.billed_hours = support_role.allocated_hours
            support_role.save()
            log_system_activity(
                job,
                "{user} support allocation marked as used.".format(
                    user=support_role.user
                ),
                author=request.user,
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False

    context = {"job": job, "instance": support_role}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_support_team_mark_used.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Job, "slug", "slug"))
def job_support_team_delete(request, slug, pk):
    job = get_object_or_404(Job, slug=slug)
    support_role = get_object_or_404(JobSupportTeamRole, pk=pk, job=job)
    data = dict()
    if request.method == "POST":
        if request.POST.get("user_action") == "approve_action":
            support_role.delete()
            log_system_activity(
                job,
                "{user} deleted from support role.".format(user=support_role.user),
                author=request.user,
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False

    context = {"job": job, "instance": support_role}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_support_team_delete.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_add_note_job", (Job, "slug", "slug"))
def job_create_note(request, slug):
    job = get_object_or_404(Job, slug=slug)
    if request.method == "POST":
        form = AddNote(request.POST)
        if form.is_valid():
            new_note = form.save(commit=False)
            new_note.content_object = job
            new_note.author = request.user
            new_note.is_system_note = False
            new_note.save()
            return HttpResponseRedirect(
                reverse("job_detail", kwargs={"slug": slug}) + "#notes"
            )
    return HttpResponseBadRequest()


class JobBaseView(ChaoticaBaseView, View):
    model = Job
    fields = "__all__"

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("job_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("job_list")

    def get_context_data(self, **kwargs):
        context = super(JobBaseView, self).get_context_data(**kwargs)
        note_form = AddNote()
        context["note_form"] = note_form
        return context


class JobListView(JobBaseView, UserPassesTestMixin, ListView):

    # We only want to allow you to view if you have a role!
    def test_func(self):
        return self.request.user.groups.all()

    def get_queryset(self):
        # Only return jobs with:
        # - permission
        # - isn't deleted
        # - isn't archived
        # get our units
        units = get_objects_for_user(
            self.request.user, "jobtracker.can_view_jobs", klass=OrganisationalUnit
        )
        jobs = (
            Job.objects.filter(Q(unit__in=units))
            .exclude(status=JobStatuses.DELETED)
            .exclude(status=JobStatuses.ARCHIVED)
        )
        return jobs


class JobDetailView(JobPermissionRequiredMixin, JobBaseView, DetailView):
    permission_required = "jobtracker.can_view_jobs"
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(JobDetailView, self).get_context_data(**kwargs)

        scope_inline_form = ScopeInlineForm(instance=context["job"])
        context["scopeInlineForm"] = scope_inline_form

        return context


class JobCreateView(UnitPermissionRequiredMixin, JobBaseView, CreateView):
    permission_required = "jobtracker.can_add_job"
    return_403 = True
    template_name = "jobtracker/job_form.html"
    form_class = JobForm
    fields = None

    def get_permission_object(self):
        orgs = OrganisationalUnit.objects.filter(
            pk__in=self.request.user.unit_memberships.filter(
                # roles__in=UnitRoles.get_roles_with_permission("jobtracker.can_add_job")
            )
            .values_list("unit")
            .distinct()
        ).first()  # return any - it doesn't matter here!
        return orgs

    def get_initial(self):
        self.initial.update({"created_by": self.request.user})
        return self.initial

    def get_success_url(self):
        return reverse_lazy("job_detail", kwargs={"slug": self.object.slug})

    def get_form_kwargs(self):
        kwargs = super(JobCreateView, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.save()
        log_system_activity(
            form.instance, "Created Job", author=form.instance.created_by
        )
        return super().form_valid(form)


class JobUpdateView(UnitPermissionRequiredMixin, JobBaseView, UpdateView):
    permission_required = "jobtracker.can_update_job"
    return_403 = True
    template_name = "jobtracker/job_form.html"
    form_class = JobForm
    fields = None
    """View to update a job"""

    def get_form_kwargs(self):
        kwargs = super(JobUpdateView, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def form_valid(self, form):
        log_system_activity(form.instance, "Job Updated")
        return super().form_valid(form)


class JobUpdateScopeView(UnitPermissionRequiredMixin, JobBaseView, UpdateView):
    permission_required = "jobtracker.can_scope_jobs"
    return_403 = True
    model = Job
    template_name = "jobtracker/job_form_scope.html"
    form_class = ScopeForm
    fields = None

    def get_form_kwargs(self):
        kwargs = super(JobUpdateView, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def form_valid(self, form):
        log_system_activity(form.instance, "Scope Updated")
        return super().form_valid(form)


class JobScheduleView(UnitPermissionRequiredMixin, JobBaseView, DetailView):
    permission_required = "jobtracker.view_job_schedule"
    return_403 = True
    """ Renders the schedule for the job """
    template_name = "jobtracker/job_schedule.html"

    def get_context_data(self, **kwargs):
        context = super(JobScheduleView, self).get_context_data(**kwargs)
        context["userSelect"] = AssignUserField()
        context["TimeSlotDeliveryRoles"] = TimeSlotDeliveryRole.CHOICES

        types_in_use = context["job"].get_all_total_scheduled_by_type()
        context["TimeSlotDeliveryRolesInUse"] = types_in_use
        return context


class JobDeleteView(UnitPermissionRequiredMixin, JobBaseView, DeleteView):
    permission_required = "jobtracker.can_delete_job"
    return_403 = True
    """View to delete a job"""


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "slug"))
def job_update_workflow(request, slug, new_state):
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    new_state_str = None
    try:
        for state in JobStatuses.CHOICES:
            if state[0] == new_state:
                new_state_str = state[1]
        if new_state_str == None:
            raise TypeError()
    except Exception:
        return HttpResponseBadRequest()

    can_proceed = True

    if new_state == JobStatuses.PENDING_SCOPE:
        if job.can_to_pending_scope(request):
            if request.method == "POST":
                job.to_pending_scope(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.SCOPING:
        if job.can_to_scoping(request):
            if request.method == "POST":
                if not job.scoped_by.all():
                    if request.user.has_perm("can_scope_jobs", job.unit):
                        # No one is defined to scope and we have permission - auto add!
                        job.scoped_by.add(request.user)
                        job.save()
                job.to_scoping(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED:
        if job.can_to_additional_scope_req(request):
            if request.method == "POST":
                job.to_additional_scope_req(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.PENDING_SCOPING_SIGNOFF:
        if job.can_to_scope_pending_signoff(request):
            if request.method == "POST":
                job.to_scope_pending_signoff(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.SCOPING_COMPLETE:
        if job.can_to_scope_complete(request):
            if request.method == "POST":
                job.to_scope_complete(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.PENDING_START:
        if job.can_to_pending_start(request):
            if request.method == "POST":
                job.to_pending_start(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.IN_PROGRESS:
        if job.can_to_in_progress(request):
            if request.method == "POST":
                job.to_in_progress(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.COMPLETED:
        if job.can_to_complete(request):
            if request.method == "POST":
                job.to_complete(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.LOST:
        if job.can_to_lost(request):
            if request.method == "POST":
                job.to_lost(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.DELETED:
        if job.can_to_delete(request):
            if request.method == "POST":
                job.to_delete(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.ARCHIVED:
        if job.can_to_archive(request):
            if request.method == "POST":
                job.to_archive(request.user)
        else:
            can_proceed = False
    else:
        return HttpResponseBadRequest()

        # sendWebHookStatusAlert(redteam=rt, title="Engagement Status Changed", msg="Engagement "+rt.projectName+" status has changed to: "+str(dict(RTState.choices).get(new_state)))

    if request.method == "POST" and can_proceed:
        job.save()
        data["form_is_valid"] = (
            True  # This is just to play along with the existing code
        )

    tasks = WorkflowTask.objects.filter(
        appliedModel=WorkflowTask.WF_JOB, status=new_state
    )
    context = {
        "job": job,
        "can_proceed": can_proceed,
        "new_state_str": new_state_str,
        "new_state": new_state,
        "tasks": tasks,
    }
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_workflow.html", context, request=request
    )
    return JsonResponse(data)


################################################
## Job Autocompletes
################################################


class JobBillingCodeAutocomplete(autocomplete.Select2QuerySetView):

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return BillingCode.objects.none()

        job_slug = self.forwarded.get("slug", None)
        if not job_slug:
            return BillingCode.objects.none()

        # TODO: return only if job allowed
        job = Job.objects.get(slug=job_slug)

        qs = BillingCode.objects.filter(Q(client=job.client) | Q(client__isnull=True))

        if self.q:
            qs = qs.filter(code__istartswith=self.q)

        return qs

    def get_result_label(self, result):
        return result.get_html_label()


class JobAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return Job.objects.none()

        units_with_job_perms = get_objects_for_user(
            self.request.user, "jobtracker.can_view_jobs", OrganisationalUnit
        )

        qs = Job.objects.filter(
            unit__in=units_with_job_perms,
        )
        if self.q:
            qs = qs.filter(
                Q(title__icontains=self.q)
                | Q(overview__icontains=self.q)
                | Q(slug__icontains=self.q)
                | Q(id__icontains=self.q),
            )
        return qs
