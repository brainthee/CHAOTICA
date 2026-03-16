from django.shortcuts import get_object_or_404
from django.http import HttpResponseBadRequest, JsonResponse
from django.template import loader
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.db.models import Count
from django.contrib.auth.decorators import login_required
from chaotica_utils.views import ChaoticaBaseView
from notifications.utils import AppNotification, send_notifications
from notifications.enums import NotificationTypes
from chaotica_utils.models import User
from ..models import (
    OrganisationalUnit,
    OrganisationalUnitMember,
    OrganisationalUnitRole,
    Job,
    Phase,
)
from ..enums import PhaseStatuses
from chaotica_utils.enums import UnitRoles
from chaotica_utils.utils import get_week
from ..decorators import unit_permission_required_or_403
from ..forms import (
    OrganisationalUnitForm,
    OrganisationalUnitMemberForm,
    OrganisationalUnitMemberRolesForm,
)
from ..mixins import PrefetchRelatedMixin
from ..utils import get_scheduler_members, get_scheduler_slots
import logging
from django.contrib import messages
from django.utils import timezone
import datetime, json
from guardian.decorators import permission_required_or_403
from guardian.mixins import PermissionRequiredMixin
from qa_reviews.models import QAReview


logger = logging.getLogger(__name__)


class OrganisationalUnitBaseView(ChaoticaBaseView):
    model = OrganisationalUnit
    fields = "__all__"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("organisationalunit_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("organisationalunit_list")


class OrganisationalUnitListView(
    PrefetchRelatedMixin, PermissionRequiredMixin, OrganisationalUnitBaseView, ListView
):
    prefetch_related = [
        "jobs",
        "members",
    ]
    permission_required = "jobtracker.view_organisationalunit"


class OrganisationalUnitDetailView(
    PrefetchRelatedMixin,
    PermissionRequiredMixin,
    OrganisationalUnitBaseView,
    DetailView,
):
    prefetch_related = []
    permission_required = "jobtracker.view_organisationalunit"
    accept_global_perms = True

    def get_queryset(self):
        return super().get_queryset().select_related("lead")

    def get_object(self, queryset=None):
        # Cache to avoid re-evaluating queryset + prefetches on every call
        # (guardian check_permissions, DetailView.get, and get_context_data all call this)
        if not hasattr(self, "_cached_object"):
            self._cached_object = super().get_object(queryset)
        return self._cached_object

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        unit = self.object

        # Pre-compute active membership check (avoids get_activeMembers query in template)
        context["is_active_member"] = unit.members.filter(
            member=self.request.user,
            left_date__isnull=True,
        ).exists()

        # Evaluate memberships once with proper prefetches
        context["active_memberships"] = list(unit.get_activeMemberships())

        # Add QA review data for users with permission
        if self.request.user.has_perm("can_view_all_reviews", unit):
            # In progress reviews for this unit
            context['in_progress_reviews'] = list(
                QAReview.objects.filter(
                    phase__job__unit=unit,
                    status__in=['started', 'in_progress']
                ).select_related(
                    'phase', 'reviewer', 'reviewed_user', 'phase__job'
                ).order_by('-started_at')
            )

            # Recent completed reviews (last 30 days)
            thirty_days_ago = timezone.now() - datetime.timedelta(days=30)
            context['recent_reviews'] = list(
                QAReview.objects.filter(
                    phase__job__unit=unit,
                    status='completed',
                    completed_at__gte=thirty_days_ago
                ).select_related(
                    'phase', 'reviewer', 'reviewed_user', 'phase__job'
                ).order_by('-completed_at')[:10]
            )

        return context


@login_required
@permission_required_or_403(
    "jobtracker.view_organisationalunit",
    (OrganisationalUnit, "slug", "slug"),
)
def orgunit_stats_partial(request, slug):
    unit = get_object_or_404(OrganisationalUnit, slug=slug)
    context = {}

    date_range_raw = request.GET.get("dateRange", "")
    if " to " in date_range_raw:
        date_range_split = date_range_raw.split(" to ")
        if len(date_range_split) == 2:
            context["start_date"] = timezone.datetime.strptime(
                date_range_split[0], "%Y-%m-%d"
            ).date()
            context["end_date"] = timezone.datetime.strptime(
                date_range_split[1], "%Y-%m-%d"
            ).date()

    if "start_date" not in context:
        context["start_date"] = request.GET.get(
            "start_date",
            (timezone.now() - datetime.timedelta(days=30)).date(),
        )
        context["end_date"] = request.GET.get(
            "end_date", timezone.now().date()
        )

    context["stats"] = unit.get_stats(context["start_date"], context["end_date"])
    context["stats_json"] = json.dumps(context["stats"], indent=4, default=str)
    context["organisationalunit"] = unit

    html = loader.render_to_string(
        "partials/unit/unit_stats.html", context, request=request
    )
    return JsonResponse({"html": html, "stats_json": context["stats_json"]})


@login_required
@permission_required_or_403(
    "jobtracker.view_organisationalunit",
    (OrganisationalUnit, "slug", "slug"),
)
def orgunit_jobs_partial(request, slug):
    unit = get_object_or_404(OrganisationalUnit, slug=slug)
    job_list = list(
        unit.jobs.annotate(phase_count=Count("phases")).select_related("client")
    )
    html = loader.render_to_string(
        "partials/job/job_list_table.html",
        {"job_list": job_list, "disableAjax": True},
        request=request,
    )
    return JsonResponse({"html": html})


KANBAN_COLUMNS = [
    {"title": "Scoping", "underline": "secondary", "statuses": [PhaseStatuses.DRAFT, PhaseStatuses.PENDING_SCHED]},
    {"title": "Scheduling", "underline": "warning", "statuses": [PhaseStatuses.SCHEDULED_TENTATIVE, PhaseStatuses.SCHEDULED_CONFIRMED]},
    {"title": "Pre-Delivery", "underline": "primary", "statuses": [PhaseStatuses.PRE_CHECKS, PhaseStatuses.CLIENT_NOT_READY, PhaseStatuses.READY_TO_BEGIN]},
    {"title": "In Progress", "underline": "danger", "statuses": [PhaseStatuses.IN_PROGRESS]},
    {"title": "QA", "underline": "info", "statuses": [PhaseStatuses.PENDING_TQA, PhaseStatuses.QA_TECH, PhaseStatuses.QA_TECH_AUTHOR_UPDATES, PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES, PhaseStatuses.QA_PRES_AUTHOR_UPDATES]},
    {"title": "Completed", "underline": "success", "statuses": [PhaseStatuses.COMPLETED]},
    {"title": "Delivered", "underline": "success", "statuses": [PhaseStatuses.DELIVERED]},
]

KANBAN_EXCLUDED_STATUSES = [
    PhaseStatuses.CANCELLED,
    PhaseStatuses.POSTPONED,
    PhaseStatuses.DELETED,
    PhaseStatuses.ARCHIVED,
]


@login_required
@permission_required_or_403(
    "jobtracker.view_organisationalunit",
    (OrganisationalUnit, "slug", "slug"),
)
def orgunit_board_partial(request, slug):
    unit = get_object_or_404(OrganisationalUnit, slug=slug)
    phases = list(
        Phase.objects.filter(job__unit=unit)
        .exclude(status__in=KANBAN_EXCLUDED_STATUSES)
        .select_related("job", "job__client", "service", "project_lead")
        .order_by("status", "_start_date")
    )

    status_to_phases = {}
    for phase in phases:
        status_to_phases.setdefault(phase.status, []).append(phase)

    columns = []
    for col_def in KANBAN_COLUMNS:
        col_phases = []
        for s in col_def["statuses"]:
            col_phases.extend(status_to_phases.get(s, []))
        columns.append({
            "title": col_def["title"],
            "underline": col_def["underline"],
            "phases": col_phases,
            "count": len(col_phases),
        })

    html = loader.render_to_string(
        "partials/unit/unit_board.html",
        {"columns": columns},
        request=request,
    )
    return JsonResponse({"html": html})


class OrganisationalUnitDeleteView(
    PermissionRequiredMixin, OrganisationalUnitBaseView, DeleteView
):
    permission_required = "jobtracker.delete_organisationalunit"


class OrganisationalUnitUpdateView(
    PermissionRequiredMixin, OrganisationalUnitBaseView, UpdateView
):
    permission_required = "jobtracker.change_organisationalunit"
    form_class = OrganisationalUnitForm
    fields = None


class OrganisationalUnitCreateView(
    PermissionRequiredMixin, OrganisationalUnitBaseView, CreateView
):
    permission_required = "jobtracker.add_organisationalunit"
    permission_object = OrganisationalUnit
    form_class = OrganisationalUnitForm
    fields = None

    def form_valid(self, form):
        # ensure the lead has manager access
        super_response = super(OrganisationalUnitCreateView, self).form_valid(form)
        org_unit = form.save()
        management_role = OrganisationalUnitRole.objects.filter(
            manage_role=True
        ).first()
        lead, _ = OrganisationalUnitMember.objects.get_or_create(
            unit=org_unit, member=org_unit.lead
        )
        lead.roles.add(management_role)
        # Also add self in case we're not the lead
        if self.request.user is not org_unit.lead:
            r_user, _ = OrganisationalUnitMember.objects.get_or_create(
                unit=org_unit, member=self.request.user
            )
            r_user.roles.add(management_role)
        return super_response


@permission_required_or_403(
    "jobtracker.manage_members", (OrganisationalUnit, "slug", "slug")
)
def organisationalunit_add(request, slug):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)

    data = dict()
    if request.method == "POST":
        form = OrganisationalUnitMemberForm(request.POST, org_unit=org_unit)
        if form.is_valid():
            membership = form.save(commit=False)
            # lets check if they already exist...
            if OrganisationalUnitMember.objects.filter(
                member=membership.member, unit=org_unit
            ).exists():
                # Already a member - refuse it...
                form.add_error("member", "User is already a member")
                data["form_is_valid"] = False
            else:
                membership.unit = org_unit
                if membership:
                    # Ok, lets see if we need to make it pending...
                    if org_unit.approval_required:
                        messages.info(
                            request, "Request to join unit " + org_unit.name + " sent."
                        )
                    else:
                        # Add ourselves as inviter!
                        membership.inviter = request.user
                        messages.info(request, "Joined Unit " + org_unit.name)
                    membership.save()
                    data["form_is_valid"] = True
        else:
            messages.error(request, "Error requesting membership. Please report this!")
            data["form_is_valid"] = False
    else:
        form = OrganisationalUnitMemberForm(org_unit=org_unit)

    context = {"orgUnit": org_unit, "form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/organisationalunit_add.html", context, request=request
    )
    return JsonResponse(data)


def organisationalunit_join(request, slug):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)
    # Lets check they aren't already a member!
    if OrganisationalUnitMember.objects.filter(
        unit=org_unit, member=request.user, left_date__isnull=True
    ).exists():
        # Already a current member!
        return HttpResponseBadRequest()

    data = dict()
    if request.method == "POST":
        # Lets assume they want to if it's a POST!
        # Lets add the membership...
        membership = OrganisationalUnitMember.objects.create(
            unit=org_unit, member=request.user
        )
        if membership:
            # Ok, lets see if we need to make it pending...
            if org_unit.approval_required:
                membership.roles.add = OrganisationalUnitRole.objects.get(
                    pk=UnitRoles.PENDING
                )
                messages.info(
                    request, "Request to join unit " + org_unit.name + " sent."
                )
            else:
                # Add ourselves as inviter!
                membership.inviter = request.user
                messages.info(request, "Joined Unit " + org_unit.name)
            membership.save()
            data["form_is_valid"] = True
        else:
            messages.error(request, "Error requesting membership. Please report this!")
            data["form_is_valid"] = False

    context = {"orgUnit": org_unit}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/organisationalunit_join.html", context, request=request
    )
    return JsonResponse(data)


@unit_permission_required_or_403(
    "jobtracker.manage_members", (OrganisationalUnit, "slug", "slug")
)
def organisationalunit_manage_roles(request, slug, member_pk):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)
    membership = get_object_or_404(
        OrganisationalUnitMember, unit=org_unit, pk=member_pk
    )

    # Silly thing... lets not be able to modify our own account unless we're an admin
    if OrganisationalUnitMember.objects.filter(
        member=request.user, pk=member_pk
    ).exists() and not request.user.is_superuser:
        # Naughty naughty...
        return HttpResponseBadRequest()

    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        form = OrganisationalUnitMemberRolesForm(
            request.POST, instance=membership, org_unit=org_unit
        )
        if form.is_valid():
            membership = form.save()
            # Lets update the unit's permissions...
            membership.unit.sync_permissions()
            data["form_is_valid"] = True
        else:
            messages.error(request, "Error requesting membership. Please report this!")
            data["form_is_valid"] = False
    else:
        form = OrganisationalUnitMemberRolesForm(instance=membership, org_unit=org_unit)

    context = {"orgUnit": org_unit, "membership": membership, "form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/organisationalunit_manage_roles.html",
        context,
        request=request,
    )
    return JsonResponse(data)


@unit_permission_required_or_403(
    "jobtracker.manage_members", (OrganisationalUnit, "slug", "slug")
)
def organisationalunit_review_join_request(request, slug, member_pk):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)

    # Only pass if the membership is pending...
    membership = get_object_or_404(
        OrganisationalUnitMember, unit=org_unit, pk=member_pk, roles=None
    )

    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        # We need to check which button was pressed... accept or reject!
        if request.POST.get("user_action") == "approve_action":
            # Approve it!
            messages.info(request, "Accepted request from " + str(membership.member))
            membership.inviter = request.user
            default_role = OrganisationalUnitRole.objects.filter(
                default_role=True
            ).first()
            membership.roles.add(default_role)
            membership.save()
            data["form_is_valid"] = True

        elif request.POST.get("user_action") == "reject_action":
            # remove it!
            messages.warning(request, "Removed request from " + str(membership.member))
            membership.delete()
            data["form_is_valid"] = True
        else:
            # invalid choice...
            data["form_is_valid"] = False

    context = {"orgUnit": org_unit, "membership": membership}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/organisationalunit_review.html", context, request=request
    )
    return JsonResponse(data)
