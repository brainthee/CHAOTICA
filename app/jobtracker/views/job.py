from django.shortcuts import get_object_or_404, render
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
from ..mixins import UnitPermissionRequiredMixin, JobPermissionRequiredMixin, PrefetchRelatedMixin
from django.views import View
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django_select2.views import AutoResponseView
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
    Link,
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
    LinkForm,
)
from ..enums import JobStatuses, PhaseStatuses, TimeSlotDeliveryRole, DefaultTimeSlotTypes, LinkType
from ..models import ScheduleActionType
from .. import schedule_history
from .helpers import _process_assign_user, _process_assign_contact
from chaotica_utils.utils import ext_reverse
import logging


logger = logging.getLogger(__name__)

# TODO: setup events for schedule so it comes back with member's only

# TODO: Permissions for jobs needs revisiting. TLDR; deal with non unit members
# by adding them permissions directly to the job


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_slots(request, slug):
    # Delegate to the shared vis-timeline builder, hard-scoped to this job.
    from ..utils import get_scheduler_slots, merge_include_users

    job = get_object_or_404(Job, slug=slug)
    return get_scheduler_slots(
        request,
        filtered_users=merge_include_users(request, job.team_scheduled()),
        use_filter_form=False,
        scope_phases=job.phases.all(),
        hard_scope=False,   # show other commitments faded for context
    )


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_members(request, slug):
    from ..utils import get_scheduler_members, merge_include_users

    job = get_object_or_404(Job, slug=slug)
    return get_scheduler_members(
        request,
        filtered_users=merge_include_users(request, job.team_scheduled()),
        use_filter_form=False,
        role_job=job,
    )


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
        is_new = slot is None
        before = None if is_new else schedule_history.snapshot(slot)
        form = DeliveryTimeSlotModalForm(request.POST, instance=slot, slug=slug)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.slot_type = TimeSlotType.get_builtin_object(
                DefaultTimeSlotTypes.DELIVERY
            )
            slot.save()
            if is_new:
                schedule_history.record_creates(request.user, [slot])
            else:
                schedule_history.record(
                    request.user, ScheduleActionType.UPDATE,
                    [before], [schedule_history.snapshot(slot)],
                )
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


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "slug"))
def job_link_add(request, slug):
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    if request.method == "POST":
        form = LinkForm(request.POST)
        if form.is_valid():
            link = form.save()
            job.links.add(link)
            log_system_activity(job, "Link added: {}".format(link.title), author=request.user)
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = LinkForm()
    context = {"job": job, "form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_link_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "slug"))
def job_link_delete(request, slug, pk):
    job = get_object_or_404(Job, slug=slug)
    link = get_object_or_404(Link, pk=pk)
    data = dict()
    if request.method == "POST":
        job.links.remove(link)
        link.delete()
        log_system_activity(job, "Link removed: {}".format(link.title), author=request.user)
        data["form_is_valid"] = True
    context = {"job": job, "link": link}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_link_delete.html", context, request=request
    )
    return JsonResponse(data)


class JobBaseView(PrefetchRelatedMixin, ChaoticaBaseView, View):
    prefetch_related = ['notes', 'notes__author', 'phases', 'phases__timeslots']
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
    # Override parent's prefetch_related to avoid conflicts
    prefetch_related = []
    
    def get_queryset(self):
        from django.db.models import Prefetch
        from ..models import OrganisationalUnitMember, Phase, TimeSlot
        
        # Get base queryset without parent's prefetch
        qs = Job.objects.filter(slug=self.kwargs.get('slug'))
        
        # Prefetch unit memberships ordered so .first() doesn't cause extra queries
        unit_membership_qs = OrganisationalUnitMember.objects.select_related('unit').order_by(
            'member__last_name', 'member__first_name'
        )
        
        # Prefetch timeslots with users and their unit memberships
        timeslot_qs = TimeSlot.objects.select_related('user').prefetch_related(
            Prefetch('user__unit_memberships', queryset=unit_membership_qs)
        )
        
        # Prefetch phases with all related data
        phase_qs = Phase.objects.select_related(
            'service', 'report_author', 'project_lead', 'techqa_by', 'presqa_by'
        ).prefetch_related(
            Prefetch('timeslots', queryset=timeslot_qs),
            Prefetch('report_author__unit_memberships', queryset=unit_membership_qs),
            Prefetch('project_lead__unit_memberships', queryset=unit_membership_qs),
        )
        
        return qs.prefetch_related(
            'notes', 
            'notes__author', 
            'account_manager', 
            'dep_account_manager', 
            'scoped_by',
            Prefetch('phases', queryset=phase_qs),
        )

    def get_context_data(self, **kwargs):
        context = super(JobDetailView, self).get_context_data(**kwargs)

        scope_inline_form = ScopeInlineForm(instance=context["job"])
        context["scopeInlineForm"] = scope_inline_form

        context["entity_type"] = "Job"
        context["entity_id"] = context["job"].id

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
                roles__permissions__codename="can_add_job"
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


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "slug"))
def job_clone(request, slug):
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    if request.method == "POST":
        new_job = Job(
            unit=job.unit,
            client=job.client,
            account_manager=job.account_manager,
            created_by=request.user,
        )

        if request.POST.get("clone_core"):
            new_job.title = job.title
            new_job.overview = job.overview
            new_job.dep_account_manager = job.dep_account_manager
            new_job.primary_client_poc = job.primary_client_poc

        if request.POST.get("clone_financials"):
            new_job.associated_framework = job.associated_framework
            new_job.revenue = job.revenue

        if request.POST.get("clone_risk"):
            new_job.additional_kit_required = job.additional_kit_required
            new_job.kit_sourced_by_client = job.kit_sourced_by_client
            new_job.additional_kit_info = job.additional_kit_info
            new_job.is_restricted = job.is_restricted
            new_job.restricted_detail = job.restricted_detail
            new_job.bespoke_project = job.bespoke_project
            new_job.report_to_third_party = job.report_to_third_party
            new_job.is_time_limited = job.is_time_limited
            new_job.retest_included = job.retest_included
            new_job.technically_complex_test = job.technically_complex_test
            new_job.high_risk = job.high_risk
            new_job.reasons_for_high_risk = job.reasons_for_high_risk

        new_job.save()

        if request.POST.get("clone_financials"):
            new_job.charge_codes.set(job.charge_codes.all())

        if request.POST.get("clone_services"):
            new_job.indicative_services.set(job.indicative_services.all())
            new_job.additional_contacts.set(job.additional_contacts.all())

        if request.POST.get("clone_phases"):
            from ..models import Phase as PhaseModel
            from ..enums import PhaseStatuses
            for orig_phase in job.phases.all():
                new_phase = PhaseModel(
                    job=new_job,
                    status=PhaseStatuses.DRAFT,
                    title=orig_phase.title,
                    service=orig_phase.service,
                    description=orig_phase.description,
                    test_target=orig_phase.test_target,
                    comm_reqs=orig_phase.comm_reqs,
                    restrictions=orig_phase.restrictions,
                    scheduling_requirements=orig_phase.scheduling_requirements,
                    prerequisites=orig_phase.prerequisites,
                    delivery_hours=orig_phase.delivery_hours,
                    reporting_hours=orig_phase.reporting_hours,
                    mgmt_hours=orig_phase.mgmt_hours,
                    qa_hours=orig_phase.qa_hours,
                    oversight_hours=orig_phase.oversight_hours,
                    debrief_hours=orig_phase.debrief_hours,
                    contingency_hours=orig_phase.contingency_hours,
                    other_hours=orig_phase.other_hours,
                    number_of_reports=orig_phase.number_of_reports,
                    report_to_be_left_on_client_site=orig_phase.report_to_be_left_on_client_site,
                    is_testing_onsite=orig_phase.is_testing_onsite,
                    is_reporting_onsite=orig_phase.is_reporting_onsite,
                    location=orig_phase.location,
                    linkDeliverable=orig_phase.linkDeliverable,
                    linkReportData=orig_phase.linkReportData,
                    linkTechData=orig_phase.linkTechData,
                )
                new_phase.save()

        # Cross-link the original and the clone as Related links (both directions).
        link_to_clone = Link.objects.create(
            url=ext_reverse(new_job.get_absolute_url()),
            title="{}: {}".format(new_job.id, new_job.title or "Cloned job"),
            linkType=LinkType.LN_RELATED,
        )
        job.links.add(link_to_clone)
        link_to_original = Link.objects.create(
            url=ext_reverse(job.get_absolute_url()),
            title="{}: {}".format(job.id, job.title or "Original job"),
            linkType=LinkType.LN_RELATED,
        )
        new_job.links.add(link_to_original)

        log_system_activity(new_job, "Job cloned from {}".format(job), author=request.user)
        data["form_is_valid"] = True
        data["next"] = new_job.get_absolute_url()
    else:
        context = {"job": job}
        data["html_form"] = loader.render_to_string(
            "jobtracker/modals/job_clone.html", context, request=request
        )
    return JsonResponse(data)


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
        context["scheduled_users"] = context["job"].team_scheduled()
        role_names = dict(TimeSlotDeliveryRole.CHOICES)
        context["delivery_roles_in_use"] = [
            (role_id, role_names[role_id])
            for role_id, hours in types_in_use.items()
            if hours > 0 and role_id != TimeSlotDeliveryRole.NA
        ]
        from .scheduler import get_user_schedule_breakdown, get_schedule_utilisation
        context["user_breakdown"] = get_user_schedule_breakdown(context["job"])
        context["utilisation"] = get_schedule_utilisation(context["job"])
        context["hours_in_day"] = context["job"].get_hours_in_day()
        return context


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_util(request, slug):
    from .scheduler import get_schedule_utilisation
    job = get_object_or_404(Job, slug=slug)
    context = {
        "job": job,
        "utilisation": get_schedule_utilisation(job),
    }
    return render(request, "partials/scheduler/schedule_util.html", context)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_user_breakdown(request, slug):
    from .scheduler import get_user_schedule_breakdown
    job = get_object_or_404(Job, slug=slug)
    context = {
        "user_breakdown": get_user_schedule_breakdown(job),
        "hours_in_day": job.get_hours_in_day(),
    }
    return render(request, "partials/scheduler/schedule_user_breakdown.html", context)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def view_job_schedule_phase_status(request, slug):
    from .scheduler import get_schedule_utilisation
    job = get_object_or_404(Job, slug=slug)
    context = {"job": job, "utilisation": get_schedule_utilisation(job)}
    return render(request, "partials/scheduler/schedule_job_status.html", context)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def job_schedule_export(request, slug):
    from ..schedule_export import build_schedule_xlsx, job_header_rows
    job = get_object_or_404(Job, slug=slug)
    timeslots = TimeSlot.objects.filter(phase__job=job)
    filename = "schedule-{}".format(job.slug)
    title = "Schedule — {}: {}".format(job.id, job.title)
    return build_schedule_xlsx(
        timeslots, filename, title=title, header_rows=job_header_rows(job)
    )


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

    # Moving a job to LOST cascades to cancelling its phases, which deletes
    # their scheduled timeslots. Surface how much will be cleared so the UI
    # can make the user explicitly acknowledge it (BUG-006).
    warn_clear_slots = False
    slot_count = 0
    phase_count = 0
    if new_state == JobStatuses.LOST:
        affected_phases = job.phases.exclude(
            status__in=PhaseStatuses.INACTIVE_STATUSES
        )
        phase_count = affected_phases.count()
        slot_count = TimeSlot.objects.filter(phase__in=affected_phases).count()
        warn_clear_slots = slot_count > 0

    context = {
        "job": job,
        "can_proceed": can_proceed,
        "new_state_str": new_state_str,
        "new_state": new_state,
        "tasks": tasks,
        "warn_clear_slots": warn_clear_slots,
        "slot_count": slot_count,
        "phase_count": phase_count,
    }
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_workflow.html", context, request=request
    )
    return JsonResponse(data)

