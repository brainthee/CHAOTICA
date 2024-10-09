from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponseRedirect, HttpResponseBadRequest, JsonResponse
from django.template import loader
from django.views import View
from django.db.models import Q, CharField, ExpressionWrapper
from django.db.models import Value as V
from django.db.models.functions import Concat
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from ..models import Job, Phase, WorkflowTask
from ..forms import (
    AddNote,
    AssignUserField,
    PhaseDeliverInlineForm,
    FeedbackForm,
    PhasePresQAInlineForm,
    PhaseScopeFeedbackInlineForm,
    PhaseTechQAInlineForm,
    PhaseForm,
)
from ..enums import FeedbackType, PhaseStatuses, TimeSlotDeliveryRole, JobStatuses
from .helpers import _process_assign_user
from chaotica_utils.tasks import task_send_notifications
from chaotica_utils.utils import AppNotification
from chaotica_utils.enums import NotificationTypes
import logging
from dal import autocomplete
from ..decorators import unit_permission_required_or_403, job_permission_required_or_403
from ..mixins import UnitPermissionRequiredMixin, JobPermissionRequiredMixin
from chaotica_utils.utils import (
    clean_date,
)


logger = logging.getLogger(__name__)


@job_permission_required_or_403(
    "jobtracker.view_job_schedule", (Phase, "slug", "slug")
)
def view_phase_schedule_gantt_data(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    return JsonResponse(phase.get_gantt_json(), safe=False)


@job_permission_required_or_403(
    "jobtracker.view_job_schedule", (Phase, "slug", "slug")
)
def view_phase_schedule_slots(request, job_slug, slug):
    data = []
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    start = clean_date(request.GET.get("start", None))
    end = clean_date(request.GET.get("end", None))
    phase_members = phase.team()
    for member_slot in phase_members:
        data = data + member_slot.get_timeslots(start=start, end=end, phase_focus=phase)
    return JsonResponse(data, safe=False)


class PhaseAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        from pprint import pprint
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return Phase.objects.none()
        qs = Phase.objects.phases_with_unit_permission(
            self.request.user, "jobtracker.can_view_jobs"
        )
        pprint(qs)
        if self.q:
            qs = qs.filter(
                Q(title__icontains=self.q)|
                Q(phase_id__icontains=self.q)|
                Q(job__id__icontains=self.q)
            )
        pprint(qs)
        return qs


@job_permission_required_or_403(
    "jobtracker.view_job_schedule", (Phase, "slug", "slug")
)
def view_phase_schedule_members(request, job_slug, slug):
    data = []
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    scheduled_users = phase.team()
    if scheduled_users:
        for user in scheduled_users:
            role = ""
            if phase.project_lead == user:
                if role:
                    role += ",Lead"
                else:
                    role += "Lead"
            if phase.report_author == user:
                if role:
                    role += ", Author"
                else:
                    role += "Author"
            if phase.techqa_by == user:
                if role:
                    role += ", TQA"
                else:
                    role += "TQA"
            if phase.presqa_by == user:
                if role:
                    role += ", PQA"
                else:
                    role += "PQA"
            user_title = str(user)
            if role:
                user_title = user_title + " (" + role + ")"
            data.append(
                {
                    "id": user.pk,
                    "title": user_title,
                    "role": role,
                    "businessHours": {
                        "startTime": job.unit.businessHours_startTime,
                        "endTime": job.unit.businessHours_endTime,
                        "daysOfWeek": job.unit.businessHours_days,
                    },
                }
            )
    return JsonResponse(data, safe=False)


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def assign_phase_field(request, job_slug, slug, field):
    valid_fields = ["project_lead", "report_author", "techqa_by", "presqa_by"]
    phase = get_object_or_404(Phase, slug=slug, job__slug=job_slug)
    if field in valid_fields:
        return _process_assign_user(request, phase, field)
    else:
        return HttpResponseBadRequest()


class PhaseBaseView(ChaoticaBaseView, View):
    model = Phase
    fields = "__all__"
    job_slug = None

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            if "job_slug" in self.kwargs:
                job_slug = self.kwargs["job_slug"]
                return reverse_lazy(
                    "phase_detail", kwargs={"job_slug": job_slug, "slug": slug}
                )
        else:
            if "job_slug" in self.kwargs:
                job_slug = self.kwargs["job_slug"]
                return reverse_lazy("job_detail", kwargs={"slug": job_slug})

    def get_context_data(self, **kwargs):
        context = super(PhaseBaseView, self).get_context_data(**kwargs)
        if "job_slug" in self.kwargs:
            context["job"] = get_object_or_404(Job, slug=self.kwargs["job_slug"])

        note_form = AddNote()
        context["note_form"] = note_form

        return context


class PhaseDetailView(JobPermissionRequiredMixin, PhaseBaseView, DetailView):
    permission_required = "jobtracker.can_view_jobs"

    def get_context_data(self, **kwargs):
        context = super(PhaseDetailView, self).get_context_data(**kwargs)

        phase_deliver_inline_form = PhaseDeliverInlineForm(instance=context["phase"])
        context["phase_deliver_inline_form"] = phase_deliver_inline_form

        info_form = PhaseForm(instance=context["phase"])
        context["info_form"] = info_form

        feedback_form = None

        if context["phase"].status == PhaseStatuses.IN_PROGRESS:
            feedback_form = PhaseScopeFeedbackInlineForm(instance=context["phase"])

        if context["phase"].status == PhaseStatuses.QA_TECH:
            feedback_form = PhaseTechQAInlineForm(instance=context["phase"])

        if context["phase"].status == PhaseStatuses.QA_PRES:
            feedback_form = PhasePresQAInlineForm(instance=context["phase"])

        context["feedback_form"] = feedback_form

        return context


class PhaseCreateView(UnitPermissionRequiredMixin, PhaseBaseView, CreateView):
    permission_required = "jobtracker.can_add_phases"
    return_403 = True
    form_class = PhaseForm
    template_name = "jobtracker/phase_form.html"
    fields = None

    def get_permission_object(self):
        if "job_slug" in self.kwargs:
            job = get_object_or_404(Job, slug=self.kwargs["job_slug"])
            return job.unit
        return None

    def get(self, request, *args, **kwargs):
        # Check if the job is in the right stage!
        if "job_slug" in self.kwargs:
            job = get_object_or_404(Job, slug=self.kwargs["job_slug"])
            if (
                job.status <= JobStatuses.PENDING_SCOPE
                or job.status >= JobStatuses.COMPLETED
            ):
                # Outside approved range - lets nuke the call
                return HttpResponseBadRequest()

        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.job = Job.objects.get(slug=self.kwargs["job_slug"])
        form.instance.save()
        log_system_activity(form.instance, "Created")
        return super(PhaseCreateView, self).form_valid(form)

    def get_form_kwargs(self):
        kwargs = super(PhaseCreateView, self).get_form_kwargs()
        if "job_slug" in self.kwargs:
            kwargs["job"] = get_object_or_404(Job, slug=self.kwargs["job_slug"])
        return kwargs


@job_permission_required_or_403(
    "jobtracker.can_refire_notifications_job", (Phase, "slug", "slug")
)
def phase_refire_notifications(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    phase.refire_status_notification()
    return HttpResponseRedirect(
        reverse("phase_detail", kwargs={"job_slug": job_slug, "slug": slug})
    )


@job_permission_required_or_403("jobtracker.can_add_note_job", (Phase, "slug", "slug"))
def phase_create_note(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    if request.method == "POST":
        form = AddNote(request.POST)
        if form.is_valid():
            new_note = form.save(commit=False)
            new_note.content_object = phase
            new_note.author = request.user
            new_note.is_system_note = False
            new_note.save()
            # Lets send a notification to everyone except us
            users_to_notify = phase.team().exclude(pk=request.user.pk)
            email_template = "emails/phase_content.html"
            notice = AppNotification(
                NotificationTypes.PHASE,
                "{phase} - Note added to phase".format(phase=phase),
                "A note has been added: {msg}.".format(msg=new_note.content),
                email_template,
                action_link=phase.get_absolute_url() + "#notes",
                phase=phase,
            )
            task_send_notifications(notice, users_to_notify)

            return HttpResponseRedirect(
                reverse("phase_detail", kwargs={"job_slug": job_slug, "slug": slug})
                + "#notes"
            )
    return HttpResponseBadRequest()


class PhaseScheduleView(UnitPermissionRequiredMixin, PhaseBaseView, DetailView):
    """Renders the schedule for the job"""

    template_name = "jobtracker/phase_schedule.html"
    permission_required = "jobtracker.view_job_schedule"

    def get_context_data(self, **kwargs):
        context = super(PhaseScheduleView, self).get_context_data(**kwargs)
        context["userSelect"] = AssignUserField()
        context["TimeSlotDeliveryRoles"] = TimeSlotDeliveryRole.CHOICES
        context["earliest_scheduled_date"] = context["phase"].earliest_scheduled_date()

        types_in_use = context["phase"].get_all_total_scheduled_by_type()
        context["TimeSlotDeliveryRolesInUse"] = types_in_use
        return context


class PhaseUpdateView(UnitPermissionRequiredMixin, PhaseBaseView, UpdateView):
    permission_required = "jobtracker.can_update_job"
    form_class = PhaseForm
    template_name = "jobtracker/phase_form.html"
    fields = None

    def get_form_kwargs(self):
        kwargs = super(PhaseUpdateView, self).get_form_kwargs()
        if "job_slug" in self.kwargs:
            kwargs["job"] = get_object_or_404(Job, slug=self.kwargs["job_slug"])
        return kwargs


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_edit_delivery(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    if request.method == "POST":
        form = PhaseDeliverInlineForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
            return redirect("phase_detail", job_slug, slug)
        else:
            data["form_is_valid"] = False
    else:
        form = PhaseDeliverInlineForm(instance=phase)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/feedback_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_tqa_jobs", (Phase, "slug", "slug"))
def phase_feedback_techqa(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)

    data = dict()
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.author = request.user
            feedback.phase = phase
            feedback.feedbackType = FeedbackType.TECH
            feedback.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = FeedbackForm()

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/feedback_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_pqa_jobs", (Phase, "slug", "slug"))
def phase_feedback_presqa(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)

    data = dict()
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.author = request.user
            feedback.phase = phase
            feedback.feedbackType = FeedbackType.PRES
            feedback.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = FeedbackForm()

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/feedback_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_feedback_scope(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)

    data = dict()
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.author = request.user
            feedback.phase = phase
            feedback.feedbackType = FeedbackType.SCOPE
            feedback.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = FeedbackForm()

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/feedback_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_tqa_jobs", (Phase, "slug", "slug"))
def phase_rating_techqa(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)

    data = dict()
    if request.method == "POST":
        form = PhaseTechQAInlineForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
        else:
            data["form_is_valid"] = False
    else:
        form = PhaseTechQAInlineForm(instance=phase)

    context = {"feedback_form": form}
    data["html_form"] = loader.render_to_string(
        "partials/phase/widgets/feedback.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_pqa_jobs", (Phase, "slug", "slug"))
def phase_rating_presqa(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)

    data = dict()
    if request.method == "POST":
        form = PhasePresQAInlineForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
        else:
            data["form_is_valid"] = False
    else:
        form = PhasePresQAInlineForm(instance=phase)

    context = {"feedback_form": form}
    data["html_form"] = loader.render_to_string(
        "partials/phase/widgets/feedback.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_rating_scope(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)

    data = dict()
    if request.method == "POST":
        form = PhaseScopeFeedbackInlineForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
            data["changed_data"] = form.changed_data
        else:
            data["form_is_valid"] = False
    else:
        form = PhaseScopeFeedbackInlineForm(instance=phase)

    context = {"feedback_form": form}
    data["html_form"] = loader.render_to_string(
        "partials/phase/widgets/feedback.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_update_workflow(request, job_slug, slug, new_state):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    context = {}
    new_state_str = None
    try:
        for state in PhaseStatuses.CHOICES:
            if state[0] == new_state:
                new_state_str = state[1]
        if new_state_str == None:
            raise TypeError()
    except Exception:
        return HttpResponseBadRequest()

    can_proceed = True

    if new_state == PhaseStatuses.PENDING_SCHED:
        if phase.can_to_pending_sched(request):
            if request.method == "POST":
                phase.to_pending_sched(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.SCHEDULED_TENTATIVE:
        if phase.can_to_sched_tentative(request):
            if request.method == "POST":
                phase.to_sched_tentative(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.SCHEDULED_CONFIRMED:
        if phase.can_to_sched_confirmed(request):
            if request.method == "POST":
                phase.to_sched_confirmed(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.PRE_CHECKS:
        if phase.can_to_pre_checks(request):
            if request.method == "POST":
                phase.to_pre_checks(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.CLIENT_NOT_READY:
        if phase.can_to_not_ready(request):
            if request.method == "POST":
                phase.to_not_ready(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.READY_TO_BEGIN:
        if phase.can_to_ready(request):
            if request.method == "POST":
                phase.to_ready(request.user)
            if phase.prerequisites:
                context["fyi"] = "Please be aware of the following pre-requisites:"
                context["fyi_content"] = phase.prerequisites
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.IN_PROGRESS:
        if phase.can_to_in_progress(request):
            if request.method == "POST":
                phase.to_in_progress(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.PENDING_TQA:
        if phase.can_to_pending_tech_qa(request):
            if request.method == "POST":
                phase.to_pending_tech_qa(request.user)
            if phase.job.client.specific_reporting_requirements:
                context["fyi"] = (
                    "Please be aware of the following reporting requirements:"
                )
                context["fyi_content"] = (
                    phase.job.client.specific_reporting_requirements
                )
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.QA_TECH:
        if phase.can_to_tech_qa(request):
            if request.method == "POST":
                if request.user is not phase.techqa_by:
                    if request.user.has_perm("can_tqa_jobs", phase.job.unit):
                        # We're not the TQA'er but we can... lets overwrite...
                        phase.techqa_by = request.user
                        phase.save()
                    else:
                        return HttpResponseBadRequest()
                phase.to_tech_qa(request.user)
            if phase.job.client.specific_reporting_requirements:
                context["fyi"] = (
                    "Please be aware of the following reporting requirements:"
                )
                context["fyi_content"] = (
                    phase.job.client.specific_reporting_requirements
                )
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.QA_TECH_AUTHOR_UPDATES:
        if phase.can_to_tech_qa_updates(request):
            if request.method == "POST":
                phase.to_tech_qa_updates(request.user)
            if phase.job.client.specific_reporting_requirements:
                context["fyi"] = (
                    "Please be aware of the following reporting requirements:"
                )
                context["fyi_content"] = (
                    phase.job.client.specific_reporting_requirements
                )
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.PENDING_PQA:
        if phase.can_to_pending_pres_qa(request):
            if request.method == "POST":
                phase.to_pending_pres_qa(request.user)
            if phase.job.client.specific_reporting_requirements:
                context["fyi"] = (
                    "Please be aware of the following reporting requirements:"
                )
                context["fyi_content"] = (
                    phase.job.client.specific_reporting_requirements
                )
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.QA_PRES:
        if phase.can_to_pres_qa(request):
            if request.method == "POST":
                if request.user is not phase.presqa_by:
                    if request.user.has_perm("can_pqa_jobs", phase.job.unit):
                        # We're not the TQA'er but we can... lets overwrite...
                        phase.presqa_by = request.user
                        phase.save()
                    else:
                        return HttpResponseBadRequest()
                phase.to_pres_qa(request.user)
            if phase.job.client.specific_reporting_requirements:
                context["fyi"] = (
                    "Please be aware of the following reporting requirements:"
                )
                context["fyi_content"] = (
                    phase.job.client.specific_reporting_requirements
                )
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.QA_PRES_AUTHOR_UPDATES:
        if phase.can_to_pres_qa_updates(request):
            if request.method == "POST":
                phase.to_pres_qa_updates(request.user)
            if phase.job.client.specific_reporting_requirements:
                context["fyi"] = (
                    "Please be aware of the following reporting requirements:"
                )
                context["fyi_content"] = (
                    phase.job.client.specific_reporting_requirements
                )
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.COMPLETED:
        if phase.can_to_completed(request):
            if request.method == "POST":
                phase.to_completed(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.DELIVERED:
        if phase.can_to_delivered(request):
            if request.method == "POST":
                phase.to_delivered(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.CANCELLED:
        if phase.can_to_cancelled(request):
            if request.method == "POST":
                phase.to_cancelled(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.POSTPONED:
        if phase.can_to_postponed(request):
            if request.method == "POST":
                phase.to_postponed(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.DELETED:
        if phase.can_to_deleted(request):
            if request.method == "POST":
                phase.to_deleted(request.user)
        else:
            can_proceed = False
    elif new_state == PhaseStatuses.ARCHIVED:
        if phase.can_to_archived(request):
            if request.method == "POST":
                phase.to_archived(request.user)
        else:
            can_proceed = False
    else:
        return HttpResponseBadRequest()

        # sendWebHookStatusAlert(redteam=rt, title="Engagement Status Changed", msg="Engagement "+rt.projectName+" status has changed to: "+str(dict(RTState.choices).get(new_state)))

    if request.method == "POST" and can_proceed:
        phase.save()
        data["form_is_valid"] = (
            True  # This is just to play along with the existing code
        )

    tasks = WorkflowTask.objects.filter(
        appliedModel=WorkflowTask.WF_PHASE, status=new_state
    )

    context["job"] = job
    context["phase"] = phase
    context["can_proceed"] = can_proceed
    context["new_state_str"] = new_state_str
    context["new_state"] = new_state
    context["tasks"] = tasks
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/phase_workflow.html", context, request=request
    )
    return JsonResponse(data)


class PhaseDeleteView(UnitPermissionRequiredMixin, PhaseBaseView, DeleteView):
    permission_required = "jobtracker.can_delete_phases"
    """View to delete a job"""
