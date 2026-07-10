from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from django.template import loader
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.conf import settings
import csv, io, re
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.db.models import Count
from django.contrib.auth.decorators import login_required
from chaotica_utils.views import ChaoticaBaseView
from notifications.utils import AppNotification, send_notifications
from notifications.enums import NotificationTypes
from chaotica_utils.models import User, Group
from ..models import (
    OrganisationalUnit,
    OrganisationalUnitMember,
    OrganisationalUnitRole,
    Job,
    Phase,
)
from ..enums import PhaseStatuses
from chaotica_utils.enums import UnitRoles
from chaotica_utils.utils import get_week, ext_reverse
from chaotica_utils.views import page_defaults
from ..decorators import unit_permission_required_or_403
from ..forms import (
    OrganisationalUnitForm,
    OrganisationalUnitMemberForm,
    OrganisationalUnitMemberRolesForm,
    PreloadUnitMemberForm,
    ImportUnitMembersForm,
)
from ..mixins import PrefetchRelatedMixin
from ..utils import get_scheduler_members, get_scheduler_slots
import logging
from django.contrib import messages
from django.utils import timezone
import datetime, json
from chaotica_utils.decorators import permission_required_or_403
from chaotica_utils.mixins import (
    SecurePermissionRequiredMixin as PermissionRequiredMixin,
)
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
            context["in_progress_reviews"] = list(
                QAReview.objects.filter(
                    phase__job__unit=unit, status__in=["started", "in_progress"]
                )
                .select_related("phase", "reviewer", "reviewed_user", "phase__job")
                .order_by("-started_at")
            )

            # Recent completed reviews (last 30 days)
            thirty_days_ago = timezone.now() - datetime.timedelta(days=30)
            context["recent_reviews"] = list(
                QAReview.objects.filter(
                    phase__job__unit=unit,
                    status="completed",
                    completed_at__gte=thirty_days_ago,
                )
                .select_related("phase", "reviewer", "reviewed_user", "phase__job")
                .order_by("-completed_at")[:10]
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
        context["end_date"] = request.GET.get("end_date", timezone.now().date())

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
    {
        "title": "Scoping",
        "underline": "secondary",
        "statuses": [PhaseStatuses.DRAFT, PhaseStatuses.PENDING_SCHED],
    },
    {
        "title": "Scheduling",
        "underline": "warning",
        "statuses": [
            PhaseStatuses.SCHEDULED_TENTATIVE,
            PhaseStatuses.SCHEDULED_CONFIRMED,
        ],
    },
    {
        "title": "Pre-Delivery",
        "underline": "primary",
        "statuses": [
            PhaseStatuses.PRE_CHECKS,
            PhaseStatuses.CLIENT_NOT_READY,
            PhaseStatuses.READY_TO_BEGIN,
        ],
    },
    {
        "title": "In Progress",
        "underline": "danger",
        "statuses": [PhaseStatuses.IN_PROGRESS],
    },
    {
        "title": "QA",
        "underline": "info",
        "statuses": [
            PhaseStatuses.PENDING_TQA,
            PhaseStatuses.QA_TECH,
            PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
            PhaseStatuses.PENDING_PQA,
            PhaseStatuses.QA_PRES,
            PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
        ],
    },
    {
        "title": "Completed",
        "underline": "success",
        "statuses": [PhaseStatuses.COMPLETED],
    },
    {
        "title": "Delivered",
        "underline": "success",
        "statuses": [PhaseStatuses.DELIVERED],
    },
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
        columns.append(
            {
                "title": col_def["title"],
                "underline": col_def["underline"],
                "phases": col_phases,
                "count": len(col_phases),
            }
        )

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


def _preload_unit_member(
    org_unit,
    requesting_user,
    email,
    first_name="",
    last_name="",
    site_group=None,
    unit_roles=None,
    can_assign_site_roles=False,
):
    """Create (or adopt) a user by email and attach site + unit roles.

    A real ``User`` row is created up-front so that first login (SSO adopts by
    email) picks up the pre-assigned roles. Returns ``(user, user_created)``.
    Does NOT sync unit permissions — the caller should call
    ``org_unit.sync_permissions()`` once after processing (so a bulk import only
    syncs once).
    """
    email = (email or "").strip()
    user = User.objects.filter(email__iexact=email).first()
    user_created = False
    if user is None:
        user = User(
            email=email,
            first_name=(first_name or "").strip(),
            last_name=(last_name or "").strip(),
            is_active=True,
        )
        user.set_unusable_password()
        user.save()
        user_created = True

    # Site (global) role. Only an assigner with manage_user may pick an
    # elevated role; everyone else (and every new user) gets the default role.
    group_to_add = None
    if can_assign_site_roles and site_group:
        group_to_add = site_group
    elif user_created:
        group_to_add = PreloadUnitMemberForm.get_default_site_group()
    if group_to_add:
        user.groups.add(group_to_add)

    # Unit membership + roles
    membership, _ = OrganisationalUnitMember.objects.get_or_create(
        unit=org_unit, member=user
    )
    if not membership.inviter:
        membership.inviter = requesting_user
        membership.save()
    if unit_roles:
        membership.roles.add(*unit_roles)

    return user, user_created


def _send_preload_notification(user):
    """Email a pre-loaded user to let them know they have access (SSO-friendly)."""
    from constance import config
    from notifications.email import send_templated_email

    if not config.EMAIL_ENABLED:
        return
    context = {
        "SITE_DOMAIN": settings.SITE_DOMAIN,
        "SITE_PROTO": settings.SITE_PROTO,
        "title": "You've been granted access to CHAOTICA",
        "action_link": ext_reverse(reverse("login")),
    }
    send_templated_email("emails/user_preloaded.html", context, [user.email])


@permission_required_or_403(
    "jobtracker.manage_members", (OrganisationalUnit, "slug", "slug")
)
def organisationalunit_preload_member(request, slug):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)

    data = dict()
    data["form_is_valid"] = False
    if request.method == "POST":
        form = PreloadUnitMemberForm(
            request.POST, requesting_user=request.user, org_unit=org_unit
        )
        if form.is_valid():
            with transaction.atomic():
                user, created = _preload_unit_member(
                    org_unit=org_unit,
                    requesting_user=request.user,
                    email=form.cleaned_data["email"],
                    first_name=form.cleaned_data.get("first_name", ""),
                    last_name=form.cleaned_data.get("last_name", ""),
                    site_group=form.cleaned_data.get("site_role"),
                    unit_roles=form.cleaned_data.get("unit_roles"),
                    can_assign_site_roles=form.can_assign_site_roles,
                )
                org_unit.sync_permissions()
            if form.cleaned_data.get("send_email"):
                _send_preload_notification(user)
            if created:
                messages.success(
                    request, "Pre-loaded %s into %s" % (user.email, org_unit.name)
                )
            else:
                messages.success(
                    request, "Added %s to %s" % (user.email, org_unit.name)
                )
            data["form_is_valid"] = True
    else:
        form = PreloadUnitMemberForm(requesting_user=request.user, org_unit=org_unit)

    context = {"orgUnit": org_unit, "form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/organisationalunit_preload.html", context, request=request
    )
    return JsonResponse(data)


UNIT_MEMBER_CSV_HEADERS = [
    "email",
    "first_name",
    "last_name",
    "site_role",
    "unit_roles",
]


@permission_required_or_403(
    "jobtracker.manage_members", (OrganisationalUnit, "slug", "slug")
)
@require_http_methods(["GET", "POST"])
def organisationalunit_import_members(request, slug):
    from chaotica_utils.utils import email_domain_allowed

    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)
    can_assign_site_roles = request.user.has_perm("chaotica_utils.manage_user")

    if request.method == "POST":
        form = ImportUnitMembersForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = form.cleaned_data["csv_file"]
            send_email = form.cleaned_data.get("send_email")

            try:
                text_file = io.TextIOWrapper(csv_file.file, encoding="utf-8-sig")
                reader = csv.DictReader(text_file)

                normalised_headers = [
                    (f or "").strip().lower() for f in (reader.fieldnames or [])
                ]
                if "email" not in normalised_headers:
                    messages.error(request, "CSV file must include an 'email' column")
                    return redirect(
                        "organisationalunit_import_members", slug=org_unit.slug
                    )

                # Lookup maps built once
                role_by_name = {
                    r.name.strip().lower(): r
                    for r in OrganisationalUnitRole.objects.all()
                }
                default_unit_role = OrganisationalUnitRole.objects.filter(
                    default_role=True
                ).first()
                group_by_name = {
                    g.name.lower(): g
                    for g in Group.objects.filter(
                        name__startswith=settings.GLOBAL_GROUP_PREFIX
                    )
                }

                success_count = 0
                error_count = 0
                errors = []
                created_users = []

                with transaction.atomic():
                    for row_num, raw in enumerate(reader, start=2):
                        row = {
                            (k or "").strip().lower(): (v or "").strip()
                            for k, v in raw.items()
                        }
                        email = row.get("email", "")
                        if not email:
                            errors.append(f"Row {row_num}: missing email")
                            error_count += 1
                            continue

                        if not email_domain_allowed(email):
                            errors.append(
                                f"Row {row_num}: email domain not allowed ({email})"
                            )
                            error_count += 1
                            continue

                        # Unit roles (semicolon/comma separated names)
                        unit_roles = []
                        bad_role = None
                        for rn in re.split(r"[;,]", row.get("unit_roles", "")):
                            rn = rn.strip().lower()
                            if not rn:
                                continue
                            role = role_by_name.get(rn)
                            if role is None:
                                bad_role = rn
                                break
                            unit_roles.append(role)
                        if bad_role:
                            errors.append(
                                f"Row {row_num}: unknown unit role '{bad_role}'"
                            )
                            error_count += 1
                            continue
                        if not unit_roles and default_unit_role:
                            unit_roles = [default_unit_role]

                        # Site role (only honoured for privileged importers)
                        site_group = None
                        if can_assign_site_roles and row.get("site_role"):
                            label = row["site_role"].strip()
                            site_group = group_by_name.get(
                                label.lower()
                            ) or group_by_name.get(
                                (settings.GLOBAL_GROUP_PREFIX + label).lower()
                            )
                            if site_group is None:
                                errors.append(
                                    f"Row {row_num}: unknown site role '{label}'"
                                )
                                error_count += 1
                                continue

                        try:
                            user, created = _preload_unit_member(
                                org_unit=org_unit,
                                requesting_user=request.user,
                                email=email,
                                first_name=row.get("first_name", ""),
                                last_name=row.get("last_name", ""),
                                site_group=site_group,
                                unit_roles=unit_roles,
                                can_assign_site_roles=can_assign_site_roles,
                            )
                            success_count += 1
                            if created and send_email:
                                created_users.append(user)
                        except Exception as e:
                            errors.append(f"Row {row_num}: unexpected error - {e}")
                            error_count += 1

                    org_unit.sync_permissions()

                # Send emails after the transaction commits
                if send_email:
                    for user in created_users:
                        _send_preload_notification(user)

                if success_count:
                    messages.success(
                        request,
                        f"Imported {success_count} member(s) into {org_unit.name}",
                    )
                if error_count:
                    detail = errors[:5]
                    if len(errors) > 5:
                        detail.append(f"... and {len(errors) - 5} more errors")
                    messages.error(
                        request,
                        f"Failed to import {error_count} row(s). " + "; ".join(detail),
                    )

                if success_count:
                    return redirect("organisationalunit_detail", slug=org_unit.slug)

            except Exception as e:
                messages.error(request, f"Error processing CSV file: {e}")
                return redirect("organisationalunit_import_members", slug=org_unit.slug)
    else:
        form = ImportUnitMembersForm()

    context = {"orgUnit": org_unit, "form": form}
    context = {**context, **page_defaults(request)}
    template = loader.get_template("jobtracker/import_members.html")
    return HttpResponse(template.render(context, request))


@permission_required_or_403(
    "jobtracker.manage_members", (OrganisationalUnit, "slug", "slug")
)
@require_http_methods(["GET"])
def download_unit_members_template(request, slug):
    org_unit = get_object_or_404(OrganisationalUnit, slug=slug)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="unit_members_template.csv"'
    writer = csv.writer(response)
    writer.writerow(UNIT_MEMBER_CSV_HEADERS)
    writer.writerow(
        ["user@example.com", "Ada", "Lovelace", "User", "Consultant;Scoper"]
    )
    writer.writerow(["another@example.com", "Alan", "Turing", "", "Consultant"])
    return response


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
    if (
        OrganisationalUnitMember.objects.filter(
            member=request.user, pk=member_pk
        ).exists()
        and not request.user.is_superuser
    ):
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
