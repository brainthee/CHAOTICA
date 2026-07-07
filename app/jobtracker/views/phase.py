from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import HttpResponseRedirect, HttpResponseBadRequest, JsonResponse
from django.template import loader
from django.views import View
from django.db.models import Q
from django.contrib import messages
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from ..models import Job, Phase, WorkflowTask, Feedback, Link
from ..forms import (
    AddNote,
    AssignUserField,
    PhaseDeliverInlineForm,
    FeedbackForm,
    PhasePresQAInlineForm,
    PhaseScopeFeedbackInlineForm,
    PhaseTechQAInlineForm,
    PhaseForm,
    LinkForm,
)
from ..enums import FeedbackType, PhaseStatuses, TimeSlotDeliveryRole, JobStatuses, LinkType
from .helpers import _process_assign_user
from notifications.utils import AppNotification, send_notifications
from notifications.enums import NotificationTypes
import logging
from django_select2.views import AutoResponseView
from ..decorators import job_permission_required_or_403
from ..mixins import (
    UnitPermissionRequiredMixin,
    JobPermissionRequiredMixin,
    PrefetchRelatedMixin,
)
from chaotica_utils.utils import (
    clean_date,
    ext_reverse,
)


logger = logging.getLogger(__name__)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def view_phase_schedule_slots(request, job_slug, slug):
    # Delegate to the shared vis-timeline builder, hard-scoped to this phase.
    from ..utils import get_scheduler_slots, merge_include_users

    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    return get_scheduler_slots(
        request,
        filtered_users=merge_include_users(request, phase.team()),
        use_filter_form=False,
        scope_phases=[phase],
        hard_scope=False,   # show other commitments faded for context
    )


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def view_phase_schedule_members(request, job_slug, slug):
    from ..utils import get_scheduler_members, merge_include_users

    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    return get_scheduler_members(
        request,
        filtered_users=merge_include_users(request, phase.team()),
        use_filter_form=False,
        role_job=job,
        role_phase=phase,
    )


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def assign_phase_field(request, job_slug, slug, field):
    valid_fields = ["project_lead", "report_author", "techqa_by", "presqa_by"]
    phase = get_object_or_404(Phase, slug=slug, job__slug=job_slug)
    if field in valid_fields:
        return _process_assign_user(request, phase, field)
    else:
        return HttpResponseBadRequest()


class PhaseBaseView(PrefetchRelatedMixin, ChaoticaBaseView, View):
    prefetch_related = ["timeslots", "notes", "notes__author"]
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

        context["entity_type"] = "Phase"
        context["entity_id"] = context["phase"].id

        feedback_form = None

        if context["phase"].status == PhaseStatuses.IN_PROGRESS:
            feedback_form = PhaseScopeFeedbackInlineForm(instance=context["phase"])

        if context["phase"].status == PhaseStatuses.QA_TECH:
            feedback_form = PhaseTechQAInlineForm(instance=context["phase"])

        if context["phase"].status == PhaseStatuses.QA_PRES:
            feedback_form = PhasePresQAInlineForm(instance=context["phase"])

        context["feedback_form"] = feedback_form

        phase = context["phase"]
        if phase._start_date and phase._delivery_date and phase.status in PhaseStatuses.ACTIVE_STATUSES:
            context["concurrent_phases"] = Phase.objects.filter(
                job=phase.job,
                _start_date__lte=phase._delivery_date,
                _delivery_date__gte=phase._start_date,
            ).exclude(pk=phase.pk).exclude(
                status__in=[
                    PhaseStatuses.CANCELLED,
                    PhaseStatuses.POSTPONED,
                    PhaseStatuses.DELETED,
                    PhaseStatuses.ARCHIVED,
                ]
            )

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


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_update_dates(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    phase.save()
    messages.info(request, "Dates updated based on schedule")

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
            email_template = "emails/phase_content.html"

            notification = AppNotification(
                notification_type=NotificationTypes.PHASE_NEW_NOTE,
                title=f"{phase}: Note added to phase",
                message=f"A note has been added: {new_note.content}",
                email_template=email_template,
                link=phase.get_absolute_url() + "#notes",
                entity_type=phase.__class__.__name__,
                entity_id=phase.pk,
                metadata={
                    "phase": phase,
                }
            )
            send_notifications(notification)

            return HttpResponseRedirect(
                reverse("phase_detail", kwargs={"job_slug": job_slug, "slug": slug})
                + "#notes"
            )
    return HttpResponseBadRequest()


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_link_add(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    if request.method == "POST":
        form = LinkForm(request.POST)
        if form.is_valid():
            link = form.save()
            phase.links.add(link)
            log_system_activity(phase, "Link added: {}".format(link.title), author=request.user)
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = LinkForm()
    context = {"job": job, "phase": phase, "form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/phase_link_form.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_link_delete(request, job_slug, slug, pk):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    link = get_object_or_404(Link, pk=pk)
    data = dict()
    if request.method == "POST":
        phase.links.remove(link)
        link.delete()
        log_system_activity(phase, "Link removed: {}".format(link.title), author=request.user)
        data["form_is_valid"] = True
    context = {"job": job, "phase": phase, "link": link}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/phase_link_delete.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Phase, "slug", "slug"))
def phase_clone(request, job_slug, slug):
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    if request.method == "POST":
        new_phase = Phase(job=job, status=PhaseStatuses.DRAFT)

        if request.POST.get("clone_identity"):
            new_phase.title = phase.title
            new_phase.service = phase.service

        if request.POST.get("clone_scope_text"):
            new_phase.description = phase.description
            new_phase.test_target = phase.test_target
            new_phase.comm_reqs = phase.comm_reqs
            new_phase.restrictions = phase.restrictions
            new_phase.scheduling_requirements = phase.scheduling_requirements
            new_phase.prerequisites = phase.prerequisites

        if request.POST.get("clone_hours"):
            new_phase.delivery_hours = phase.delivery_hours
            new_phase.reporting_hours = phase.reporting_hours
            new_phase.mgmt_hours = phase.mgmt_hours
            new_phase.qa_hours = phase.qa_hours
            new_phase.oversight_hours = phase.oversight_hours
            new_phase.debrief_hours = phase.debrief_hours
            new_phase.contingency_hours = phase.contingency_hours
            new_phase.other_hours = phase.other_hours

        if request.POST.get("clone_dates"):
            new_phase.desired_start_date = phase.desired_start_date
            new_phase.desired_delivery_date = phase.desired_delivery_date
            new_phase.due_to_techqa_set = phase.due_to_techqa_set
            new_phase.due_to_presqa_set = phase.due_to_presqa_set

        if request.POST.get("clone_config"):
            new_phase.number_of_reports = phase.number_of_reports
            new_phase.report_to_be_left_on_client_site = phase.report_to_be_left_on_client_site
            new_phase.is_testing_onsite = phase.is_testing_onsite
            new_phase.is_reporting_onsite = phase.is_reporting_onsite
            new_phase.location = phase.location

        if request.POST.get("clone_links"):
            new_phase.linkDeliverable = phase.linkDeliverable
            new_phase.linkReportData = phase.linkReportData
            new_phase.linkTechData = phase.linkTechData

        new_phase.save()

        # Cross-link the original and the clone as Related links (both directions).
        link_to_clone = Link.objects.create(
            url=ext_reverse(new_phase.get_absolute_url()),
            title="{}: {}".format(new_phase.get_id(), new_phase.title or "Cloned phase"),
            linkType=LinkType.LN_RELATED,
        )
        phase.links.add(link_to_clone)
        link_to_original = Link.objects.create(
            url=ext_reverse(phase.get_absolute_url()),
            title="{}: {}".format(phase.get_id(), phase.title or "Original phase"),
            linkType=LinkType.LN_RELATED,
        )
        new_phase.links.add(link_to_original)

        log_system_activity(new_phase, "Phase cloned from {}".format(phase), author=request.user)
        data["form_is_valid"] = True
        data["next"] = new_phase.get_absolute_url()
    else:
        context = {"job": job, "phase": phase}
        data["html_form"] = loader.render_to_string(
            "jobtracker/modals/phase_clone.html", context, request=request
        )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def phase_schedule_export(request, job_slug, slug):
    from ..schedule_export import build_schedule_xlsx, phase_header_rows
    from ..models import TimeSlot
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    timeslots = TimeSlot.objects.filter(phase=phase)
    filename = "schedule-{}-{}".format(job.slug, phase.slug)
    title = "Schedule — {}: {}".format(phase.get_id(), phase.title)
    return build_schedule_xlsx(
        timeslots, filename, title=title, header_rows=phase_header_rows(phase)
    )


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
        context["scheduled_users"] = context["phase"].team_scheduled()
        role_names = dict(TimeSlotDeliveryRole.CHOICES)
        context["delivery_roles_in_use"] = [
            (role_id, role_names[role_id])
            for role_id, hours in types_in_use.items()
            if hours > 0 and role_id != TimeSlotDeliveryRole.NA
        ]
        from .scheduler import get_user_schedule_breakdown, get_schedule_utilisation
        context["user_breakdown"] = get_user_schedule_breakdown(
            context["job"], context["phase"]
        )
        context["utilisation"] = get_schedule_utilisation(context["job"], context["phase"])
        context["hours_in_day"] = context["phase"].get_hours_in_day()
        # Scheduling Assistant: is the phase's schedule still a draft (tentative)?
        context["schedule_is_confirmed"] = (
            context["phase"].status >= PhaseStatuses.SCHEDULED_CONFIRMED
        )
        return context


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def view_phase_schedule_user_breakdown(request, job_slug, slug):
    from .scheduler import get_user_schedule_breakdown
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    context = {
        "user_breakdown": get_user_schedule_breakdown(job, phase),
        "hours_in_day": phase.get_hours_in_day(),
    }
    return render(request, "partials/scheduler/schedule_user_breakdown.html", context)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def view_phase_team(request, job_slug, slug):
    from .scheduler import get_user_schedule_breakdown, build_team_rows
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    capacity_labels, user_breakdown = build_team_rows(
        get_user_schedule_breakdown(job, phase)
    )
    context = {
        "user_breakdown": user_breakdown,
        "capacity_labels": capacity_labels,
        "hours_in_day": phase.get_hours_in_day(),
    }
    return render(request, "partials/scheduler/team_summary.html", context)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def phase_team_export(request, job_slug, slug):
    from ..schedule_export import build_team_xlsx
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    return build_team_xlsx(job, phase)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def view_phase_schedule_util(request, job_slug, slug):
    from .scheduler import get_schedule_utilisation
    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    context = {
        "phase": phase,
        "job": job,
        "utilisation": get_schedule_utilisation(job, phase),
    }
    return render(request, "partials/scheduler/schedule_util.html", context)


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


def phase_feedback_edit(request, job_slug, slug, pk):
    feedback = get_object_or_404(Feedback, pk=pk, phase__slug=slug, author=request.user)

    data = dict()
    if request.method == "POST":
        form = FeedbackForm(request.POST, instance=feedback)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = FeedbackForm(instance=feedback)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/feedback_form.html", context, request=request
    )
    return JsonResponse(data)


def phase_feedback_delete(request, job_slug, slug, pk):
    feedback = get_object_or_404(Feedback, pk=pk, phase__slug=slug, author=request.user)
    context = {}

    data = dict()
    if request.method == "POST":
        feedback.delete()
        data["form_is_valid"] = True
    else:
        form = FeedbackForm(instance=feedback)
        context = {"form": form}

    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/feedback_form_delete.html", context, request=request
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
            rating = phase.techqa_report_rating
            if rating is not None and rating <= 1:
                recipient = None
                if phase.report_author:
                    recipient = phase.report_author.manager or phase.report_author.acting_manager
                if not recipient:
                    recipient = job.account_manager
                if recipient:
                    notification = AppNotification(
                        notification_type=NotificationTypes.PHASE_FEEDBACK,
                        title="Low Tech QA rating on {}: {}".format(
                            phase.title, phase.get_techqa_report_rating_display()
                        ),
                        message="Phase '{}' received a Tech QA rating of '{}'. Please follow up with the author.".format(
                            phase.title, phase.get_techqa_report_rating_display()
                        ),
                        link=phase.get_absolute_url(),
                    )
                    send_notifications(notification, specific_users=recipient)
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
            rating = phase.presqa_report_rating
            if rating is not None and rating <= 1:
                recipient = None
                if phase.report_author:
                    recipient = phase.report_author.manager or phase.report_author.acting_manager
                if not recipient:
                    recipient = job.account_manager
                if recipient:
                    notification = AppNotification(
                        notification_type=NotificationTypes.PHASE_FEEDBACK,
                        title="Low Pres QA rating on {}: {}".format(
                            phase.title, phase.get_presqa_report_rating_display()
                        ),
                        message="Phase '{}' received a Presentation QA rating of '{}'. Please follow up with the author.".format(
                            phase.title, phase.get_presqa_report_rating_display()
                        ),
                        link=phase.get_absolute_url(),
                    )
                    send_notifications(notification, specific_users=recipient)
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
                if request.user != phase.techqa_by:
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
                if request.user != phase.presqa_by:
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


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "job_slug"))
def phases_bulk_workflow_modal(request, job_slug, new_state):
    """
    Display modal for bulk workflow status change across all phases in a job.
    Shows which phases can proceed and which cannot.
    """
    job = get_object_or_404(Job, slug=job_slug)
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
    
    # Get all phases for this job
    phases = job.phases.all()
    
    # Check which phases can proceed to this state
    eligible_phases = []
    ineligible_phases = []
    
    for phase in phases:
        can_proceed = False
        reason = None
        
        # Check eligibility based on the new state using can_proceed_to_* methods
        # These don't trigger messages, unlike can_to_* methods
        if new_state == PhaseStatuses.PENDING_SCHED:
            can_proceed = phase.can_proceed_to_pending_sched()
        elif new_state == PhaseStatuses.SCHEDULED_TENTATIVE:
            can_proceed = phase.can_proceed_to_sched_tentative()
        elif new_state == PhaseStatuses.SCHEDULED_CONFIRMED:
            can_proceed = phase.can_proceed_to_sched_confirmed()
        elif new_state == PhaseStatuses.PRE_CHECKS:
            can_proceed = phase.can_proceed_to_pre_checks()
        elif new_state == PhaseStatuses.CLIENT_NOT_READY:
            can_proceed = phase.can_proceed_to_not_ready()
        elif new_state == PhaseStatuses.READY_TO_BEGIN:
            can_proceed = phase.can_proceed_to_ready()
        elif new_state == PhaseStatuses.IN_PROGRESS:
            can_proceed = phase.can_proceed_to_in_progress()
        elif new_state == PhaseStatuses.PENDING_TQA:
            can_proceed = phase.can_proceed_to_pending_tech_qa()
        elif new_state == PhaseStatuses.QA_TECH:
            can_proceed = phase.can_proceed_to_tech_qa()
        elif new_state == PhaseStatuses.QA_TECH_AUTHOR_UPDATES:
            can_proceed = phase.can_proceed_to_tech_qa_updates()
        elif new_state == PhaseStatuses.PENDING_PQA:
            can_proceed = phase.can_proceed_to_pending_pres_qa()
        elif new_state == PhaseStatuses.QA_PRES:
            can_proceed = phase.can_proceed_to_pres_qa()
        elif new_state == PhaseStatuses.QA_PRES_AUTHOR_UPDATES:
            can_proceed = phase.can_proceed_to_pres_qa_updates()
        elif new_state == PhaseStatuses.COMPLETED:
            can_proceed = phase.can_proceed_to_completed()
        elif new_state == PhaseStatuses.DELIVERED:
            can_proceed = phase.can_proceed_to_delivered()
        elif new_state == PhaseStatuses.CANCELLED:
            can_proceed = phase.can_proceed_to_cancelled()
        elif new_state == PhaseStatuses.POSTPONED:
            can_proceed = phase.can_proceed_to_postponed()
        elif new_state == PhaseStatuses.DELETED:
            can_proceed = phase.can_proceed_to_delete()
        elif new_state == PhaseStatuses.ARCHIVED:
            can_proceed = phase.can_proceed_to_archived()
        else:
            return HttpResponseBadRequest()
        
        if can_proceed:
            eligible_phases.append(phase)
        else:
            ineligible_phases.append(phase)
    
    # Get workflow tasks for this state
    tasks = WorkflowTask.objects.filter(
        appliedModel=WorkflowTask.WF_PHASE, status=new_state
    )
    
    context["job"] = job
    context["new_state_str"] = new_state_str
    context["new_state"] = new_state
    context["eligible_phases"] = eligible_phases
    context["ineligible_phases"] = ineligible_phases
    context["tasks"] = tasks
    context["has_eligible"] = len(eligible_phases) > 0
    
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/phases_bulk_workflow.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "job_slug"))
def phases_bulk_workflow_execute(request, job_slug, new_state):
    """
    Execute bulk workflow status change for selected phases.
    """
    if request.method != "POST":
        return HttpResponseBadRequest()
    
    job = get_object_or_404(Job, slug=job_slug)
    data = dict()
    
    # Get selected phase IDs from POST data
    phase_ids = request.POST.getlist('phase_ids[]')
    
    if not phase_ids:
        data["form_is_valid"] = False
        data["error"] = "No phases selected"
        return JsonResponse(data)
    
    # Process each selected phase
    success_count = 0
    error_count = 0
    
    for phase_id in phase_ids:
        try:
            phase = Phase.objects.get(id=phase_id, job=job)
            
            # Apply the workflow change based on new_state
            if new_state == PhaseStatuses.PENDING_SCHED:
                if phase.can_to_pending_sched(request):
                    phase.to_pending_sched(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.SCHEDULED_TENTATIVE:
                if phase.can_to_sched_tentative(request):
                    phase.to_sched_tentative(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.SCHEDULED_CONFIRMED:
                if phase.can_to_sched_confirmed(request):
                    phase.to_sched_confirmed(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.PRE_CHECKS:
                if phase.can_to_pre_checks(request):
                    phase.to_pre_checks(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.CLIENT_NOT_READY:
                if phase.can_to_not_ready(request):
                    phase.to_not_ready(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.READY_TO_BEGIN:
                if phase.can_to_ready(request):
                    phase.to_ready(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.IN_PROGRESS:
                if phase.can_to_in_progress(request):
                    phase.to_in_progress(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.PENDING_TQA:
                if phase.can_to_pending_tech_qa(request):
                    phase.to_pending_tech_qa(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.QA_TECH:
                if phase.can_to_tech_qa(request):
                    phase.to_tech_qa(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.QA_TECH_AUTHOR_UPDATES:
                if phase.can_to_tech_qa_updates(request):
                    phase.to_tech_qa_updates(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.PENDING_PQA:
                if phase.can_to_pending_pres_qa(request):
                    phase.to_pending_pres_qa(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.QA_PRES:
                if phase.can_to_pres_qa(request):
                    phase.to_pres_qa(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.QA_PRES_AUTHOR_UPDATES:
                if phase.can_to_pres_qa_updates(request):
                    phase.to_pres_qa_updates(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.COMPLETED:
                if phase.can_to_completed(request):
                    phase.to_completed(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.DELIVERED:
                if phase.can_to_delivered(request):
                    phase.to_delivered(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.CANCELLED:
                if phase.can_to_cancelled(request):
                    phase.to_cancelled(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.POSTPONED:
                if phase.can_to_postponed(request):
                    phase.to_postponed(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.DELETED:
                if phase.can_to_deleted(request):
                    phase.to_deleted(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            elif new_state == PhaseStatuses.ARCHIVED:
                if phase.can_to_archived(request):
                    phase.to_archived(request.user)
                    phase.save()
                    success_count += 1
                else:
                    error_count += 1
            else:
                error_count += 1
                
        except Phase.DoesNotExist:
            error_count += 1
            continue
    
    if success_count > 0:
        messages.success(
            request, 
            f"Successfully updated {success_count} phase(s)."
        )
    
    if error_count > 0:
        messages.warning(
            request,
            f"Failed to update {error_count} phase(s)."
        )
    
    data["form_is_valid"] = True
    return JsonResponse(data)


QA_ELIGIBLE_STATUSES = [
    PhaseStatuses.PENDING_TQA,
    PhaseStatuses.QA_TECH,
    PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
    PhaseStatuses.PENDING_PQA,
    PhaseStatuses.QA_PRES,
    PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
    PhaseStatuses.COMPLETED,
    PhaseStatuses.DELIVERED,
]


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "job_slug"))
def phases_bulk_qa_modal(request, job_slug):
    job = get_object_or_404(Job, slug=job_slug)
    data = dict()

    phases = job.phases.filter(status__in=QA_ELIGIBLE_STATUSES)
    techqa_users = job.unit.get_active_members_with_perm("can_tqa_jobs")
    presqa_users = job.unit.get_active_members_with_perm("can_pqa_jobs")

    context = {
        "job": job,
        "phases": phases,
        "techqa_users": techqa_users,
        "presqa_users": presqa_users,
    }
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/phases_bulk_qa.html", context, request=request
    )
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_update_job", (Job, "slug", "job_slug"))
def phases_bulk_qa_execute(request, job_slug):
    if request.method != "POST":
        return HttpResponseBadRequest()

    job = get_object_or_404(Job, slug=job_slug)
    data = dict()

    phase_ids = request.POST.getlist("phase_ids[]")
    if not phase_ids:
        data["form_is_valid"] = False
        data["error"] = "No phases selected"
        return JsonResponse(data)

    techqa_id = request.POST.get("techqa_by") or None
    presqa_id = request.POST.get("presqa_by") or None

    if not techqa_id and not presqa_id:
        data["form_is_valid"] = False
        data["error"] = "Select at least one QA user to assign"
        return JsonResponse(data)

    from chaotica_utils.models import User as UserModel
    techqa_user = UserModel.objects.get(pk=techqa_id) if techqa_id else None
    presqa_user = UserModel.objects.get(pk=presqa_id) if presqa_id else None

    # Validate the posted assignees against the same QA-capable member sets the
    # modal offers, so a crafted POST can't assign QA to a user who lacks the
    # Tech/Pres QA permission on this job's unit.
    if techqa_user and techqa_user not in set(
        job.unit.get_active_members_with_perm("can_tqa_jobs")
    ):
        data["form_is_valid"] = False
        data["error"] = "Selected Tech QA user can't perform Tech QA for this job."
        return JsonResponse(data)
    if presqa_user and presqa_user not in set(
        job.unit.get_active_members_with_perm("can_pqa_jobs")
    ):
        data["form_is_valid"] = False
        data["error"] = "Selected Pres QA user can't perform Pres QA for this job."
        return JsonResponse(data)

    updated = 0
    for phase_id in phase_ids:
        try:
            phase = Phase.objects.get(id=phase_id, job=job, status__in=QA_ELIGIBLE_STATUSES)
            if techqa_user:
                phase.techqa_by = techqa_user
            if presqa_user:
                phase.presqa_by = presqa_user
            phase.save()
            updated += 1
        except Phase.DoesNotExist:
            continue

    data["form_is_valid"] = True
    return JsonResponse(data)


# --------------------------------------------------------------------------- #
# Scheduling Assistant                                                          #
# --------------------------------------------------------------------------- #

# GET params that toggle optional ranking signals on/off (skill + availability
# window are always on). Absent entirely => first load => all signals on.
_ASSISTANT_SIGNAL_TOGGLES = {
    "onboarding": "sig_onboarding",
    "history": "sig_history",
    "seniority": "sig_seniority",
    "qualifications": "sig_quals",
    "availability_pct": "sig_avail_pct",
}


def _assistant_weights(request):
    """Build a weights dict from the modal's signal toggles. On first load (no
    toggle params present) every signal keeps its default weight."""
    from ..scheduling_assistant import DEFAULT_WEIGHTS

    weights = dict(DEFAULT_WEIGHTS)
    toggles_present = "toggled" in request.GET or any(
        p in request.GET for p in _ASSISTANT_SIGNAL_TOGGLES.values()
    )
    if toggles_present:
        for key, param in _ASSISTANT_SIGNAL_TOGGLES.items():
            if request.GET.get(param) not in ("1", "on", "true", "True"):
                weights[key] = 0
    return weights, toggles_present


def _assistant_scoped_pool(request):
    """Permission-scoped, optionally filter-narrowed candidate pool (reuses the
    scheduler's SchedulerFilter + _filter_users_on_query)."""
    from ..utils import _filter_users_on_query
    from ..forms import SchedulerFilter

    filter_form = SchedulerFilter(request.GET)
    filter_form.is_valid()  # populates cleaned_data; all fields are optional
    cleaned = filter_form.cleaned_data or {}
    return _filter_users_on_query(request, cleaned), filter_form


def _assistant_signal_states(request, toggles_present):
    """Per-signal on/off state for rendering the modal checkboxes. Before any
    toggle submission every optional signal defaults to on."""
    return {
        key: (not toggles_present) or (request.GET.get(param) in ("1", "on", "true", "True"))
        for key, param in _ASSISTANT_SIGNAL_TOGGLES.items()
    }


def _assistant_int(request, name, default=None):
    try:
        v = request.GET.get(name)
        return int(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


@job_permission_required_or_403("jobtracker.view_job_schedule", (Phase, "slug", "slug"))
def phase_scheduling_assistant(request, job_slug, slug):
    """Suggest ranked people to deliver a phase. Returns an AJAX modal (html_form)
    or, with ?format=json, the raw ranked candidates."""
    from ..scheduling_assistant import (
        rank_candidates_for_phase,
        phase_required_working_days,
        phase_delivery_day_stats,
    )
    import math as _math

    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)

    pool, filter_form = _assistant_scoped_pool(request)
    weights, toggles_present = _assistant_weights(request)

    # Work with what's left to schedule, not the whole scope: default the planning
    # length to the REMAINING delivery days (scoped − already-scheduled) so the
    # scheduler can "continue" an existing plan.
    stats = phase_delivery_day_stats(phase)
    default_total = max(0, _math.ceil(stats["remaining"])) if stats["remaining"] > 0 else 0

    # A phase is often split across several testers rather than one person for the
    # whole duration. "total_days" is what we're planning now (defaults to the
    # remaining); "people" is how many to split across; each candidate is then
    # ranked on availability for a per-person segment.
    total_days = _assistant_int(request, "total_days")
    if total_days is None:
        total_days = default_total
    people = max(1, _assistant_int(request, "people", 1))
    per_person_days = max(1, -(-max(total_days, 1) // people))  # ceil(total / people)

    candidates = rank_candidates_for_phase(
        phase,
        required_working_days=per_person_days,
        candidate_pool=pool,
        weights=weights,
    )
    required_days = per_person_days

    if request.GET.get("format") == "json":
        return JsonResponse(
            {
                "candidates": [
                    {
                        "id": c.user.pk,
                        "name": str(c.user),
                        "score": c.score,
                        "tier": c.tier,
                        "tier_label": c.tier_label,
                        "earliest_start": c.earliest_start.isoformat() if c.earliest_start else None,
                        "earliest_end": c.earliest_end.isoformat() if c.earliest_end else None,
                        "availability_pct": c.availability_pct,
                        "onboarding_status": c.onboarding_status,
                        "history_count": c.history_count,
                        "on_phase": c.on_phase,
                        "phase_roles": c.phase_roles,
                        "missing_required_quals": c.missing_required_quals,
                        "signals": {
                            n: {
                                "label": s.label if isinstance(s.label, str) else "",
                                "contribution": s.contribution,
                            }
                            for n, s in c.signals.items()
                        },
                    }
                    for c in candidates
                ]
            },
            safe=False,
        )

    data = {
        "html_form": loader.render_to_string(
            "partials/scheduler/scheduling_assistant_modal.html",
            {
                "job": job,
                "phase": phase,
                "service": phase.service,
                "candidates": candidates,
                "required_days": required_days,
                "total_days": total_days,
                "people": people,
                "stats": stats,
                "signal_states": _assistant_signal_states(request, toggles_present),
                "scope": "phase",
                "filter_form": filter_form,
            },
            request=request,
        )
    }
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.view_job_schedule", (Job, "slug", "slug"))
def job_scheduling_assistant(request, slug):
    """Discovery view: rank people per indicative service on a job."""
    from ..scheduling_assistant import rank_candidates_for_job, DEFAULT_JOB_DEFAULT_DAYS

    job = get_object_or_404(Job, slug=slug)
    pool, filter_form = _assistant_scoped_pool(request)
    weights, toggles_present = _assistant_weights(request)

    try:
        required_days = (
            int(request.GET.get("days")) if request.GET.get("days") else DEFAULT_JOB_DEFAULT_DAYS
        )
    except (TypeError, ValueError):
        required_days = DEFAULT_JOB_DEFAULT_DAYS

    results = rank_candidates_for_job(
        job,
        required_working_days=required_days,
        candidate_pool=pool,
        weights=weights,
    )

    data = {
        "html_form": loader.render_to_string(
            "partials/scheduler/scheduling_assistant_modal.html",
            {
                "job": job,
                "results": results,
                "required_days": required_days,
                "signal_states": _assistant_signal_states(request, toggles_present),
                "scope": "job",
                "filter_form": filter_form,
            },
            request=request,
        )
    }
    return JsonResponse(data)


@job_permission_required_or_403("jobtracker.can_schedule_job", (Phase, "slug", "slug"))
def phase_scheduling_assistant_plan(request, job_slug, slug):
    """Draft a split team for a phase from a set of selected people.

    GET  -> renders the editable planner (coverage model + per-person role/dates).
    POST -> creates the proposed bookings as tentative ("draft") delivery slots.
    """
    from datetime import datetime as _datetime, date as _date
    from django.utils import timezone
    from django.utils.html import strip_tags
    from chaotica_utils.models import User
    from ..scheduling_assistant import (
        build_split_plan,
        working_day_end,
        DEFAULT_BUSINESS_DAYS,
        phase_delivery_day_stats,
    )
    from ..enums import DefaultTimeSlotTypes, TimeSlotDeliveryRole
    from ..models import TimeSlot, TimeSlotType
    from .scheduler import _evaluate_delivery_slot

    job = get_object_or_404(Job, slug=job_slug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    business_days = job.unit.businessHours_days or list(DEFAULT_BUSINESS_DAYS)

    coverage = request.GET.get("coverage") or request.POST.get("coverage") or "sequential"
    if coverage not in ("sequential", "parallel"):
        coverage = "sequential"

    if request.method == "POST":
        slot_type = TimeSlotType.objects.get(pk=DefaultTimeSlotTypes.DELIVERY)

        def _rows(name):
            # Accept both "row_user" and jQuery's default "row_user[]" encoding.
            return request.POST.getlist(name) or request.POST.getlist(name + "[]")

        users = _rows("row_user")
        roles = _rows("row_role")
        starts = _rows("row_start")
        days_list = _rows("row_days")

        created, blocked = [], []
        lead_user = author_user = None
        # Create sequentially so each slot's scope check sees the ones already
        # drafted in this batch — this is what surfaces over-scheduling.
        for uid, role, start_s, days_s in zip(users, roles, starts, days_list):
            try:
                user = User.objects.get(pk=int(uid))
                start_date = _date.fromisoformat(start_s)
                days = max(1, int(days_s))
            except (ValueError, User.DoesNotExist):
                continue
            if role in ("lead", "lead_author"):
                lead_user = user
            if role in ("author", "lead_author"):
                author_user = user
            end_date = working_day_end(start_date, days, business_days)
            wh = user.get_working_hours()
            start_dt = timezone.make_aware(_datetime.combine(start_date, wh["start"]))
            end_dt = timezone.make_aware(_datetime.combine(end_date, wh["end"]))
            slot = TimeSlot(
                user=user,
                phase=phase,
                slot_type=slot_type,
                deliveryRole=TimeSlotDeliveryRole.DELIVERY,
                start=start_dt,
                end=end_dt,
            )
            # Run the FULL logic checks with no bypass: any failure (over-scope,
            # overlap, onboarding, framework) blocks that booking. The scheduler
            # must resolve it, not force past it.
            ev = _evaluate_delivery_slot(slot, request, force=False, check_overlaps=True)
            if ev["failed"]:
                reason = strip_tags(ev["feedback"] or "").strip()
                reason = " ".join(reason.split())  # collapse whitespace
                blocked.append({"name": user.get_full_name(), "reason": reason[:300]})
                continue
            slot.save()
            created.append(user.get_full_name())

        # Mirror the one-click role assignment: set Lead / Author on the phase.
        role_changes = []
        if lead_user and phase.project_lead_id != lead_user.pk:
            phase.project_lead = lead_user
            role_changes.append("Project Lead")
        if author_user and phase.report_author_id != author_user.pk:
            phase.report_author = author_user
            role_changes.append("Report Author")
        if role_changes:
            phase.save()
            log_system_activity(
                phase,
                "Set {} while drafting a split team".format(", ".join(role_changes)),
                author=request.user,
            )

        summary = "Drafted {} booking{} as tentative.".format(
            len(created), "" if len(created) == 1 else "s"
        )
        if blocked:
            summary += " {} blocked by scheduling checks — resolve and retry.".format(len(blocked))
        return JsonResponse(
            {
                "form_is_valid": bool(created) and not blocked,
                "created": created,
                "blocked": blocked,
                "summary": summary,
            }
        )

    # GET: build the default plan and render the editable planner.
    import math as _math
    user_ids = [int(x) for x in request.GET.get("users", "").split(",") if x.strip().isdigit()]
    stats = phase_delivery_day_stats(phase)
    default_total = max(1, _math.ceil(stats["remaining"])) if stats["remaining"] > 0 else 1
    total_days = _assistant_int(request, "total_days") or default_total
    lead_id = _assistant_int(request, "lead")
    author_id = _assistant_int(request, "author")
    start_str = request.GET.get("start")
    try:
        start_date = _date.fromisoformat(start_str) if start_str else None
    except ValueError:
        start_date = None
    if not start_date:
        start_date = phase.start_date or timezone.now().date()
    if start_date < timezone.now().date():
        start_date = timezone.now().date()

    plan = build_split_plan(
        user_ids=user_ids,
        coverage=coverage,
        total_days=total_days,
        start_date=start_date,
        lead_id=lead_id,
        author_id=author_id,
        business_days=business_days,
    )
    users_by_id = {u.pk: u for u in User.objects.filter(pk__in=user_ids)}
    rows = [
        {
            "user": users_by_id.get(r["user_id"]),
            "user_id": r["user_id"],
            "role": r["role"],
            "start": r["start"],
            "days": r["days"],
            "end": r["end"],
        }
        for r in plan
        if r["user_id"] in users_by_id
    ]

    data = {
        "html_form": loader.render_to_string(
            "partials/scheduler/scheduling_assistant_plan.html",
            {
                "job": job,
                "phase": phase,
                "rows": rows,
                "coverage": coverage,
                "total_days": total_days,
                "lead_id": lead_id or (rows[0]["user_id"] if rows else None),
                "author_id": author_id,
            },
            request=request,
        )
    }
    return JsonResponse(data)
