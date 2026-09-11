from django.urls import reverse_lazy, reverse
from django.template import loader
from django.utils import timezone
from django.http import (
    HttpResponseForbidden,
    JsonResponse,
    HttpResponse,
    HttpResponseRedirect,
    Http404,
    HttpResponseBadRequest,
)
import json
from ..forms import (
    ChaoticaUserForm,
    EditProfileForm,
    AssignRoleForm,
    MergeUserForm,
)
from ..mixins import PrefetchRelatedMixin
from ..enums import GlobalRoles
from ..models import User, Language, UserInvitation, Group
from ..utils import (
    ext_reverse,
    clean_fullcalendar_datetime,
    can_manage_user,
    group_permissions,
)
from .common import ChaoticaBaseGlobalRoleView, page_defaults
from django.conf import settings as django_settings
from django.contrib.auth.models import Permission
from guardian.shortcuts import get_user_perms
from django.contrib.auth.decorators import login_required
from chaotica_utils.decorators import permission_required_or_403
from django.views.generic.list import ListView
from django.contrib import messages
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView
from django.shortcuts import get_object_or_404
import datetime
from django.views.decorators.http import (
    require_http_methods,
    require_safe,
)


class UserBaseView(ChaoticaBaseGlobalRoleView):
    model = User
    fields = "__all__"
    success_url = reverse_lazy("user_list")
    role_required = GlobalRoles.ADMIN

    def get_context_data(self, **kwargs):
        context = super(UserBaseView, self).get_context_data(**kwargs)
        return context

    def get_queryset(self):
        queryset = User.objects.all().exclude(email="AnonymousUser")
        return queryset


class UserListView(PrefetchRelatedMixin, UserBaseView, ListView):
    prefetch_related = ["groups", "unit_memberships", "unit_memberships__unit"]
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

    def get_context_data(self, **kwargs):
        context = super(UserBaseView, self).get_context_data(**kwargs)
        invite_list = UserInvitation.objects.filter(accepted=False)
        context["invite_list"] = invite_list
        return context


class UserDetailView(UserBaseView, DetailView):
    role_required = "*"  # Allow all users with a role to view "public profiles"

    def get_object(self, queryset=None):
        if self.kwargs.get("email"):
            return get_object_or_404(
                User.objects.all().prefetch_related(
                    "timeslots",
                    "unit_memberships",
                    "skills",
                ),
                email=self.kwargs.get("email"),
            )
        else:
            raise Http404()

    def get_context_data(self, **kwargs):
        from jobtracker.models import TimeSlot

        context = super(UserDetailView, self).get_context_data(**kwargs)

        date_range_raw = self.request.GET.get("dateRange", "")
        if " to " in date_range_raw:
            date_range_split = date_range_raw.split(" to ")
            if len(date_range_split) == 2:
                context["start_date"] = timezone.datetime.strptime(
                    date_range_split[0], "%Y-%m-%d"
                )
                context["end_date"] = timezone.datetime.strptime(
                    date_range_split[1], "%Y-%m-%d"
                )

        if "start_date" not in context:
            context["start_date"] = self.request.GET.get(
                "start_date",
                (timezone.now().date() - datetime.timedelta(days=30)),
            )
            context["end_date"] = self.request.GET.get(
                "end_date", timezone.now().date()
            )

        org_raw = self.request.GET.get("org", None)
        if org_raw and org_raw.isdigit():
            if self.get_object().unit_memberships.filter(unit__pk=org_raw).exists():
                context["org"] = (
                    self.get_object().unit_memberships.get(unit__pk=org_raw).unit
                )

        if "org" not in context:
            context["org"] = None

        context["stats"] = self.get_object().get_stats(
            context["org"], context["start_date"], context["end_date"]
        )
        context["stats_json"] = json.dumps(
            context["stats"], indent=4, sort_keys=True, default=str
        )

        context["schedule_history"] = TimeSlot.history.filter(
            user=self.get_object()
        ).prefetch_related("history_user")

        # Effective permissions panel - admin-only (sensitive), read-only.
        prefix = django_settings.GLOBAL_GROUP_PREFIX
        is_admin = self.request.user.groups.filter(
            name=prefix + GlobalRoles.CHOICES[GlobalRoles.ADMIN][1]
        ).exists()
        context["can_view_permissions"] = is_admin
        context["can_view_allocation"] = self.get_object().can_be_managed_by(
            self.request.user
        )
        if is_admin:
            context["user_permissions"] = self._get_effective_permissions(
                self.get_object(), prefix
            )
        return context

    def _get_effective_permissions(self, user_obj, prefix):
        """Resolve a user's effective permissions from live state (read-only).

        Combines their global role groups with the guardian object permissions
        granted per organisational unit membership.
        """
        from django.contrib.contenttypes.models import ContentType
        from jobtracker.models import OrganisationalUnit, OrganisationalUnitMember

        # Global roles (site-wide Django groups).
        global_groups = user_obj.groups.filter(name__startswith=prefix)
        global_roles = []
        for grp in global_groups:
            role_int = grp.getGlobalRoleINT()
            global_roles.append(
                {
                    "label": (
                        GlobalRoles.CHOICES[role_int][1]
                        if role_int is not None
                        else grp.name
                    ),
                    "colour": grp.role_bs_colour() or "secondary",
                }
            )
        global_perms = group_permissions(
            Permission.objects.filter(group__in=global_groups).distinct()
        )

        # Per-unit object permissions (guardian), from active memberships.
        memberships = (
            OrganisationalUnitMember.objects.filter(
                member=user_obj, left_date__isnull=True
            )
            .select_related("unit")
            .prefetch_related("roles")
        )
        # get_user_perms() returns a values_list of codenames; resolve them back
        # to Permission rows (unit object perms belong to the unit content type).
        unit_ct = ContentType.objects.get_for_model(OrganisationalUnit)
        units = []
        for ms in memberships:
            codenames = list(get_user_perms(user_obj, ms.unit))
            perms = Permission.objects.filter(
                content_type=unit_ct, codename__in=codenames
            )
            units.append(
                {
                    "unit": ms.unit,
                    "roles": ms.roles.all(),
                    "permissions": group_permissions(perms),
                }
            )

        return {
            "global_roles": global_roles,
            "global_permissions": global_perms,
            "units": units,
        }


@login_required
@require_safe
def view_own_profile(request):
    # Redirect to public profile
    return HttpResponseRedirect(redirect_to=request.user.get_absolute_url())


def _parse_allocation_range(request):
    """Parse the ``dateRange`` / ``start_date`` / ``end_date`` GET params.

    Mirrors the convention used by ``team_stats_partial`` / ``UserDetailView``.
    Defaults to the next four weeks (a forward-looking allocation view).
    """
    start = end = None
    date_range_raw = request.GET.get("dateRange", "")
    if " to " in date_range_raw:
        parts = date_range_raw.split(" to ")
        if len(parts) == 2:
            try:
                start = datetime.datetime.strptime(parts[0], "%Y-%m-%d").date()
                end = datetime.datetime.strptime(parts[1], "%Y-%m-%d").date()
            except ValueError:
                start = end = None
    # Also accept discrete start_date / end_date params (the picker form posts
    # these) as a fallback.
    if start is None or end is None:
        try:
            if request.GET.get("start_date"):
                start = datetime.datetime.strptime(
                    request.GET["start_date"], "%Y-%m-%d"
                ).date()
            if request.GET.get("end_date"):
                end = datetime.datetime.strptime(
                    request.GET["end_date"], "%Y-%m-%d"
                ).date()
        except ValueError:
            start = end = None
    if start is None or end is None:
        # Default to the current configurable timesheet period (e.g. 1st–14th /
        # 15th–end) rather than an arbitrary rolling window.
        from ..utils import period_for_date

        start, end = period_for_date(timezone.now().date())
    return start, end


@login_required
def user_code_allocation(request, email):
    """"Code Allocations" for a user: which billing code(s) to book against,
    on which days, for how many hours.

    Deliberately not a timesheet — it reads the schedule against the effective
    billing-code assignments. Visible to the user themselves and to anyone who
    can manage them (unit managers / leads), reusing
    :meth:`User.can_be_managed_by`.
    """
    target = get_object_or_404(User, email=email)
    if not target.can_be_managed_by(request.user):
        return HttpResponseForbidden()

    start, end = _parse_allocation_range(request)
    allocation = target.get_billing_allocation(start, end)

    # per_code is keyed by code id; present as a sorted list for the template.
    per_code = sorted(
        allocation["per_code"].values(),
        key=lambda c: str(c["code"].code).lower(),
    )

    # Explain the duplicate-code handling when it actually applies to this view.
    from ..utils.billing_allocation import duplicate_code_policy

    dup_policy = duplicate_code_policy()
    has_multi_code_day = any(
        sum(1 for e in entries if e["code"]) > 1
        for entries in allocation["per_day"].values()
    )
    from constance import config

    site_date_format = config.SITE_DATE_FORMAT

    # Support-team budget. Money/LCR are gated PER JOB on the finance permission
    # for that job's unit — a viewer who can see costs in one unit must not see a
    # different unit's budget money just because it appears on this page.
    support_budget = target.get_support_budget(start, end)
    is_super = request.user.is_superuser
    for entry in support_budget["per_job"]:
        entry["can_view_money"] = is_super or request.user.has_perm(
            "jobtracker.can_view_loaded_costs", entry["job"].unit
        )
    # Whether to render the money column at all (any row visible).
    can_view_loaded_costs = any(
        e["can_view_money"] for e in support_budget["per_job"]
    )

    # Period navigation (prev/next jump by whole timesheet periods, anchored on
    # the current start date).
    from ..utils import next_period, previous_period, period_for_date

    prev_start, prev_end = previous_period(start)
    next_start, next_end = next_period(start)
    cur_start, cur_end = period_for_date(timezone.now().date())

    context = page_defaults(request)
    context.update(
        {
            "userProfile": target,
            "start_date": start,
            "end_date": end,
            "date_range": "{} to {}".format(start, end),
            "prev_start": prev_start,
            "prev_end": prev_end,
            "next_start": next_start,
            "next_end": next_end,
            "current_period_start": cur_start,
            "current_period_end": cur_end,
            "is_current_period": (start == cur_start and end == cur_end),
            "per_day": allocation["per_day"],
            "per_code": per_code,
            "uncoded": allocation["uncoded"],
            "alloc_stats": allocation["stats"],
            "dup_policy": dup_policy,
            "has_multi_code_day": has_multi_code_day,
            "site_date_format": site_date_format,
            "support_budget": support_budget,
            "can_view_loaded_costs": can_view_loaded_costs,
        }
    )
    return HttpResponse(
        loader.render_to_string(
            "chaotica_utils/user_code_allocation.html", context, request=request
        )
    )


@login_required
def user_support_draw(request, email, role_pk):
    """Cash out (draw down) support-budget hours from the user's own Billing
    Codes page.

    Self-service: gated on the same self-or-manager rule as the allocations page
    (``can_be_managed_by``), NOT on the job's ``can_schedule_job`` — a support
    member draws down their own budget without needing scheduling rights on the
    job. The role must belong to the profile owner (``user=target``)."""
    from jobtracker.models import JobSupportTeamRole
    from jobtracker.forms import SupportBudgetDrawForm
    from ..utils import period_for_date

    target = get_object_or_404(User, email=email)
    if not target.can_be_managed_by(request.user):
        return HttpResponseForbidden()
    support_role = get_object_or_404(JobSupportTeamRole, pk=role_pk, user=target)

    data = dict()
    if request.method == "POST":
        form = SupportBudgetDrawForm(request.POST)
        if form.is_valid():
            draw = form.save(commit=False)
            draw.support_role = support_role
            draw.user = target
            draw.created_by = request.user
            draw.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        from decimal import Decimal
        from chaotica_utils.utils.support_budget import build_job_support_budget

        # Pre-fill the period the page is showing (falls back to the current one),
        # and the hours with the member's remaining budget — one-click cash-out.
        def _d(value):
            try:
                return datetime.datetime.strptime(value, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                return None

        p_start = _d(request.GET.get("start"))
        p_end = _d(request.GET.get("end"))
        if not (p_start and p_end):
            p_start, p_end = period_for_date(timezone.now().date())

        initial = {"period_start": p_start, "period_end": p_end}
        budget = build_job_support_budget(support_role.job, on_date=p_end)
        member = budget["per_member"].get(support_role.user_id)
        remaining = member.get("remaining_hours") if member else None
        if remaining is not None and remaining > 0:
            initial["hours_drawn"] = remaining.quantize(Decimal("0.01"))
        form = SupportBudgetDrawForm(initial=initial)

    context = {"form": form, "job": support_role.job, "instance": support_role}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_support_team_draw.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def user_support_auto_draw(request, email):
    """One-click cash out: fill the viewed period across ALL the user's support
    roles with each role's remaining budget.

    Only creates a draw for a role that has no draw yet in this period (so it's
    safe to click again). Same self/manager gate as the allocations page.
    """
    from decimal import Decimal
    from jobtracker.models import JobSupportTeamRole, SupportBudgetDraw
    from jobtracker.enums import JobStatuses
    from chaotica_utils.utils.support_budget import build_job_support_budget
    from ..utils import period_for_date

    target = get_object_or_404(User, email=email)
    if not target.can_be_managed_by(request.user):
        return HttpResponseForbidden()

    def _d(value):
        try:
            return datetime.datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    p_start = _d(request.POST.get("start"))
    p_end = _d(request.POST.get("end"))
    if not (p_start and p_end):
        p_start, p_end = period_for_date(timezone.now().date())

    roles = JobSupportTeamRole.objects.filter(
        user=target, job__status__in=JobStatuses.ACTIVE_STATUSES
    ).select_related("job")
    created = 0
    for role in roles:
        budget = build_job_support_budget(role.job, on_date=p_end)
        member = budget["per_member"].get(target.id)
        remaining = member.get("remaining_hours") if member else None
        if not remaining or remaining <= 0:
            continue
        _obj, was_created = SupportBudgetDraw.objects.get_or_create(
            support_role=role,
            period_start=p_start,
            period_end=p_end,
            defaults={
                "user": target,
                "hours_drawn": remaining.quantize(Decimal("0.01")),
                "created_by": request.user,
            },
        )
        if was_created:
            created += 1

    if created:
        messages.success(
            request, "Cashed out {} support {} for {} – {}.".format(
                created, "role" if created == 1 else "roles", p_start, p_end
            )
        )
    else:
        messages.info(request, "Nothing to cash out for this period.")

    url = reverse("user_code_allocation", kwargs={"email": target.email})
    return HttpResponseRedirect(
        "{}?start={}&end={}".format(url, p_start, p_end)
    )


@login_required
@require_safe
def update_own_profile(request):
    # Redirect to public profile
    return HttpResponseRedirect(
        redirect_to=reverse("update_profile", kwargs={"email": request.user.email})
    )


@login_required
@require_safe
def update_own_theme(request):
    if "mode" in request.GET:
        mode = request.GET.get("mode", "light")
        valid_modes = ["dark", "light", "auto"]
        if mode in valid_modes:
            request.user.site_theme = mode
            request.user.save()
            return HttpResponse("OK")
    return HttpResponseForbidden()


@login_required
@require_http_methods(["POST"])
def create_own_api_token(request):
    """Create the caller's personal API token if they don't have one yet.

    DRF's ``authtoken`` is one token per user, stored retrievably, so this is a
    non-destructive get-or-create. An API token acts entirely as its owner: it
    inherits exactly the same permissions and object scoping the user has in the
    UI, and can never do more.
    """
    from rest_framework.authtoken.models import Token

    _, created = Token.objects.get_or_create(user=request.user)
    if created:
        from ..audit import record_audit
        from ..models import AuditVerb, AuditCategory

        record_audit(
            request.user,
            AuditVerb.TOKEN_ISSUED,
            message="API token created",
            category=AuditCategory.AUTH,
            request=request,
        )
        messages.success(request, "API token created.")
    else:
        messages.info(request, "You already have an API token.")
    return HttpResponseRedirect(reverse("view_own_profile") + "#api-tokens")


@login_required
def reset_own_api_token(request):
    """Regenerate the caller's API token (invalidates the previous key)."""
    from rest_framework.authtoken.models import Token

    data = {"form_is_valid": False}
    if request.method == "POST" and request.POST.get("user_action") == (
        "approve_action"
    ):
        Token.objects.filter(user=request.user).delete()
        Token.objects.create(user=request.user)
        from ..audit import record_audit
        from ..models import AuditVerb, AuditCategory

        record_audit(
            request.user,
            AuditVerb.TOKEN_ISSUED,
            message="API token regenerated (previous key revoked)",
            category=AuditCategory.AUTH,
            request=request,
        )
        messages.success(request, "API token regenerated. The old key no longer works.")
        data["form_is_valid"] = True
        data["next"] = reverse("view_own_profile") + "#api-tokens"

    data["html_form"] = loader.render_to_string(
        "modals/api_token_reset.html", {}, request=request
    )
    return JsonResponse(data)


@login_required
def revoke_own_api_token(request):
    """Delete the caller's API token entirely (revoke API access)."""
    from rest_framework.authtoken.models import Token

    data = {"form_is_valid": False}
    if request.method == "POST" and request.POST.get("user_action") == (
        "approve_action"
    ):
        Token.objects.filter(user=request.user).delete()
        from ..audit import record_audit
        from ..models import AuditVerb, AuditCategory

        record_audit(
            request.user,
            AuditVerb.TOKEN_REVOKED,
            message="API token revoked",
            category=AuditCategory.AUTH,
            request=request,
        )
        messages.info(request, "API token revoked.")
        data["form_is_valid"] = True
        data["next"] = reverse("view_own_profile") + "#api-tokens"

    data["html_form"] = loader.render_to_string(
        "modals/api_token_revoke.html", {}, request=request
    )
    return JsonResponse(data)


@login_required
@require_http_methods(["GET", "POST"])
def update_profile(request, email):
    from jobtracker.models import Skill
    from ..utils import can_manage_job_level
    from ..models import JobLevel, UserJobLevel
    from ..forms.job_levels import UpdateUserJobLevelForm

    usr = can_manage_user(request.user, email)
    if not usr:
        return HttpResponseForbidden()

    # Check if user can manage job levels
    can_manage_levels = can_manage_job_level(request.user, usr)
    current_job_level = UserJobLevel.get_current_level(usr)

    if request.method == "POST":
        form = EditProfileForm(
            request.POST, request.FILES, current_request=request, instance=usr
        )

        # Handle job level assignment if user has permission
        if can_manage_levels:
            job_level_form = UpdateUserJobLevelForm(request.POST)
            if job_level_form.is_valid():
                job_level = job_level_form.cleaned_data.get("job_level_id")
                job_level_notes = job_level_form.cleaned_data.get("job_level_notes", "")
                clear_job_level = job_level_form.cleaned_data.get(
                    "clear_job_level", False
                )

                if job_level:
                    # Only create new assignment if it's different from current
                    if (
                        not current_job_level
                        or current_job_level.job_level != job_level
                    ):
                        UserJobLevel.assign_level(
                            user=usr, job_level=job_level, notes=job_level_notes
                        )
                        messages.success(
                            request, f"Job level updated to {job_level.short_label}"
                        )
                elif clear_job_level and current_job_level:
                    # Mark current level as inactive if clearing
                    current_job_level.is_current = False
                    current_job_level.save()
                    messages.success(request, "Job level cleared")

        if form.is_valid():
            obj = form.save()
            obj.profile_last_updated = timezone.now().today()
            obj.save()
            if "location" in form.changed_data:
                obj.update_latlong()
            usr.refresh_from_db()
            current_job_level = UserJobLevel.get_current_level(usr)  # Refresh job level
    else:
        # Send the modal
        form = EditProfileForm(current_request=request, instance=usr)

    # Create job level form for display
    if can_manage_levels:
        job_level_form = UpdateUserJobLevelForm()
    else:
        job_level_form = None

    context = {
        "usr": usr,
        "skills": Skill.objects.all()
        .prefetch_related("category")
        .order_by("category", "name"),
        "user_skills": {us.skill_id: us for us in usr.skills.all()},
        "languages": Language.objects.all(),
        "current_job_level": current_job_level,
        "can_manage_job_level": can_manage_levels,
        "job_level_form": job_level_form,
    }

    if usr == request.user:
        # Only show the feed keys if it's us!
        context["feed_url"] = ext_reverse(
            reverse(
                "view_own_schedule_feed",
                kwargs={"cal_key": usr.schedule_feed_id},
            )
        )
        context["feed_family_url"] = ext_reverse(
            reverse(
                "view_own_schedule_feed_family",
                kwargs={"cal_key": usr.schedule_feed_family_id},
            )
        )
        # Personal API token (one per user; None until they create one).
        from rest_framework.authtoken.models import Token

        context["api_token"] = Token.objects.filter(user=usr).first()

    context["profileForm"] = form
    template = loader.get_template("update_profile.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["GET", "POST"])
def update_skills(request, email):
    from jobtracker.models import Skill, UserSkill

    data = {}
    usr = can_manage_user(request.user, email)
    if not usr:
        return HttpResponseForbidden()

    if request.method == "POST":
        # Check if this is an improvement update
        if request.POST.get("action") == "update_improvement":
            skill_slug = request.POST.get("skill_slug")
            interested = request.POST.get("interested_in_improving") == "1"

            try:
                skill = Skill.objects.get(slug=skill_slug)
                user_skill, created = UserSkill.objects.get_or_create(
                    user=usr,
                    skill=skill,
                    defaults={"rating": 0},  # Default to no experience if creating new
                )
                user_skill.interested_in_improving_skill = interested
                user_skill.last_updated_on = timezone.now()
                user_skill.save()
            except Skill.DoesNotExist:
                data["error"] = "Invalid skill"
                return JsonResponse(data, status=400)
        else:
            # Handle regular skill rating updates
            for field in request.POST:
                # Skip CSRF token and other non-skill fields
                if field in [
                    "csrfmiddlewaretoken",
                    "action",
                    "skill_slug",
                    "interested_in_improving",
                ]:
                    continue

                # get skill..
                try:
                    skill = Skill.objects.get(slug=field)
                    value = int(request.POST.get(field))

                    user_skill, created = UserSkill.objects.get_or_create(
                        user=usr, skill=skill
                    )
                    if user_skill.rating != value:
                        user_skill.rating = value
                        user_skill.last_updated_on = timezone.now()
                        user_skill.save()
                except (Skill.DoesNotExist, ValueError, TypeError):
                    # invalid skill or value!
                    pass

    data["result"] = True
    return JsonResponse(data)


@login_required
@require_http_methods(["GET", "POST"])
def update_certs(request, email):
    usr = can_manage_user(request.user, email)
    if not usr:
        return HttpResponseForbidden()

    return HttpResponseBadRequest()


@login_required
@require_http_methods(["GET"])
def view_onboarding(request, email):
    usr = can_manage_user(request.user, email)
    if not usr:
        return HttpResponseForbidden()

    context = {}
    template = loader.get_template("onboarded_clients.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["GET", "POST"])
def renew_onboarding(request, email, pk):
    usr = can_manage_user(request.user, email)
    if not usr:
        return HttpResponseForbidden()

    from jobtracker.models import ClientOnboarding

    onboarding = get_object_or_404(ClientOnboarding, user=usr, pk=pk)
    context = {}
    data = dict()
    if request.method == "POST":
        onboarding.reqs_completed = timezone.now()
        onboarding.save()
        data["form_is_valid"] = True

    context = {"onboarding": onboarding}
    data["html_form"] = loader.render_to_string(
        "modals/user_renew_onboarding.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET", "POST"])
def user_merge(request, email):
    user = get_object_or_404(User, email=email)
    context = {}
    data = dict()
    if request.method == "POST":
        form = MergeUserForm(request.POST)
        if form.is_valid():
            # Lets merge!
            user_to_merge = form.cleaned_data["user_to_merge"]
            if user_to_merge == user:
                # Same user. GTFO
                data["form_is_valid"] = False
                form.add_error("user_to_merge", "You can't merge to the same user!")
            else:
                if user.merge(user_to_merge):
                    # Success
                    data["form_is_valid"] = True
                    messages.success(request, "User merged")
                else:
                    # Merge failed!
                    data["form_is_valid"] = False
                    form.add_error("", "Failed to merge!")
    else:
        # Send the modal
        form = MergeUserForm()

    context = {"form": form, "user": user}
    data["html_form"] = loader.render_to_string(
        "modals/user_merge.html", context, request=request
    )
    return JsonResponse(data)


@login_required
def user_schedule_timeslots(request, email):
    user = get_object_or_404(User, email=email)
    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    data = user.get_timeslots(
        start=start,
        end=end,
    )
    return JsonResponse(data, safe=False)


@login_required
def user_schedule_holidays(request, email):
    user = get_object_or_404(User, email=email)
    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    data = user.get_holidays(
        start=start,
        end=end,
    )
    return JsonResponse(data, safe=False)


@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET", "POST"])
def user_manage_status(request, email, state):
    if state not in ["activate", "deactivate"]:
        return HttpResponseBadRequest()

    u = get_object_or_404(User, email=email)
    data = dict()
    if request.method == "POST":
        # set_active_status is the shared source of truth (also used by the
        # /api/v1/ set-status action); it returns False for a no-op request.
        data["form_is_valid"] = u.set_active_status(state == "activate")

    context = {"u": u, "state": state}
    data["html_form"] = loader.render_to_string(
        "modals/user_manage_status.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET", "POST"])
def user_assign_global_role(request, email):
    user = get_object_or_404(User, email=email)
    data = dict()
    if request.method == "POST":
        form = AssignRoleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = AssignRoleForm(instance=user)

    context = {
        "form": form,
    }
    data["html_form"] = loader.render_to_string(
        "modals/assign_user_role.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_safe
def user_feedback_summary(request, email):
    """Display feedback summary for a specific user's authored reports"""
    user = get_object_or_404(User, email=email)

    # Handle date range filtering
    start_date = None
    end_date = None

    # Check for date range in request
    date_range_raw = request.GET.get("dateRange", "")
    if " to " in date_range_raw:
        date_range_split = date_range_raw.split(" to ")
        if len(date_range_split) == 2:
            try:
                start_date = timezone.datetime.strptime(
                    date_range_split[0], "%Y-%m-%d"
                ).date()
                end_date = timezone.datetime.strptime(
                    date_range_split[1], "%Y-%m-%d"
                ).date()
            except ValueError:
                # Invalid date format, ignore
                pass

    # Fallback to individual date parameters
    if not start_date:
        start_date_param = request.GET.get("start_date")
        if start_date_param:
            try:
                start_date = timezone.datetime.strptime(
                    start_date_param, "%Y-%m-%d"
                ).date()
            except ValueError:
                pass

    if not end_date:
        end_date_param = request.GET.get("end_date")
        if end_date_param:
            try:
                end_date = timezone.datetime.strptime(end_date_param, "%Y-%m-%d").date()
            except ValueError:
                pass

    # Default to last 12 months if no dates specified
    if not start_date and not end_date:
        end_date = timezone.now().date()
        start_date = end_date - datetime.timedelta(days=365)

    # Get user's authored reports with QA data
    reports = (
        user.get_reports()
        .select_related("techqa_by", "presqa_by", "service", "job")
        .prefetch_related("job__client", "feedback__author")
    )

    # Apply date filtering if dates are provided
    if start_date:
        reports = reports.filter(actual_completed_date__gte=start_date)
    if end_date:
        reports = reports.filter(actual_completed_date__lte=end_date)

    # Calculate summary statistics
    total_reports = reports.count()
    techqa_ratings = [
        r.techqa_report_rating for r in reports if r.techqa_report_rating is not None
    ]
    presqa_ratings = [
        r.presqa_report_rating for r in reports if r.presqa_report_rating is not None
    ]

    avg_techqa_rating = (
        sum(techqa_ratings) / len(techqa_ratings) if techqa_ratings else None
    )
    avg_presqa_rating = (
        sum(presqa_ratings) / len(presqa_ratings) if presqa_ratings else None
    )

    # Calculate combined average if both ratings exist
    combined_avg_rating = None
    if avg_techqa_rating and avg_presqa_rating:
        combined_avg_rating = (avg_techqa_rating + avg_presqa_rating) / 2

    # Format date range for display
    date_range_display = ""
    if start_date and end_date:
        date_range_display = (
            f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )

    context = {
        "user_profile": user,
        "reports": reports,
        "total_reports": total_reports,
        "techqa_reports_count": len(techqa_ratings),
        "presqa_reports_count": len(presqa_ratings),
        "avg_techqa_rating": avg_techqa_rating,
        "avg_presqa_rating": avg_presqa_rating,
        "combined_avg_rating": combined_avg_rating,
        "start_date": start_date,
        "end_date": end_date,
        "date_range_display": date_range_display,
    }

    template = loader.get_template("chaotica_utils/user_feedback_summary.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))
