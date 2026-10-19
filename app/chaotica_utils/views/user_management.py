from django.utils.dateparse import parse_date
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
from django.core.exceptions import PermissionDenied
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
    free_hours_in_period,
    group_permissions,
)
from .common import ChaoticaBaseGlobalRoleView, page_defaults, log_system_activity
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
from decimal import Decimal
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
        # Cached: get_context_data uses it several times.
        if not hasattr(self, "_object"):
            self._object = self._get_object()
        return self._object

    def _get_object(self):
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

        # ?dateRange=YYYY-MM-DD to YYYY-MM-DD, or ?start_date= / ?end_date=;
        # anything unparseable falls back to the last 30 days (it used to 500,
        # or hand raw strings to get_stats).
        today = timezone.now().date()
        start_raw = self.request.GET.get("start_date")
        end_raw = self.request.GET.get("end_date")
        date_range_parts = self.request.GET.get("dateRange", "").split(" to ")
        if len(date_range_parts) == 2:
            start_raw, end_raw = date_range_parts
        def _date(raw):
            try:
                return parse_date(raw) if raw else None
            except ValueError:  # well-formed but impossible, e.g. 2026-02-30
                return None

        start = _date(start_raw)
        end = _date(end_raw)
        context["start_date"] = start or today - datetime.timedelta(days=30)
        context["end_date"] = end or today

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
        # Same rule as the Schedule tab's feeds and the schedule export.
        try:
            _get_schedule_viewable_user(self.request, self.get_object().email)
            context["can_view_schedule"] = True
        except PermissionDenied:
            context["can_view_schedule"] = False
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
    """Billing-period GET params → ``(start, end)`` (shared with the team /
    org-unit billing tabs)."""
    from ..utils.periods import parse_period_range

    return parse_period_range(request.GET)


# Support codes listed per day on the Billing Codes page before "+N more".
SUPPORT_CODES_PER_DAY = 3


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
    # Per-day table: support can span hundreds of codes a day, so show the
    # first few and roll the rest into one "+N more" line (the Per code table
    # still has the full split).
    per_day_rows = {}
    for day, entries in allocation["per_day"].items():
        shown, hidden, support_shown = [], [], 0
        for entry in entries:
            if entry.get("kind") == "support":
                if support_shown >= SUPPORT_CODES_PER_DAY:
                    hidden.append(entry)
                    continue
                support_shown += 1
            shown.append(entry)
        per_day_rows[day] = {
            "entries": shown,
            "support_more": {
                "count": len(hidden),
                "hours": sum((e["hours"] for e in hidden), Decimal(0)),
            }
            if hidden
            else None,
        }

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

    # Period navigation (prev/next jump by whole timesheet periods).
    from ..utils.periods import period_nav_context

    context = page_defaults(request)
    context.update(period_nav_context(start, end))
    context.update(
        {
            "userProfile": target,
            "date_range": "{} to {}".format(start, end),
            "per_day": per_day_rows,
            "period_free_hours": free_hours_in_period(
                target, start, end, stats=allocation["stats"]
            ),
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
    from decimal import Decimal
    from django.core.exceptions import ValidationError
    from jobtracker.models import JobSupportTeamRole
    from jobtracker.forms import SupportBudgetDrawForm
    from ..utils import period_for_date, create_support_draw
    from ..utils.support_budget import remaining_hours_for_role, support_draw_message

    target = get_object_or_404(User, email=email)
    if not target.can_be_managed_by(request.user):
        return HttpResponseForbidden()
    support_role = get_object_or_404(JobSupportTeamRole, pk=role_pk, user=target)

    data = dict()
    if request.method == "POST":
        form = SupportBudgetDrawForm(request.POST)
        if form.is_valid():
            try:
                draw = create_support_draw(
                    support_role,
                    form.cleaned_data["period_start"],
                    form.cleaned_data["period_end"],
                    form.cleaned_data["hours_drawn"],
                    created_by=request.user,
                )
            except ValidationError as e:
                form.add_error(None, e)
            else:
                log_system_activity(
                    support_role.job,
                    support_draw_message(target, draw),
                    author=request.user,
                )
        data["form_is_valid"] = not form.errors
        if form.errors:
            data["form_errors"] = form.errors
    else:
        # Pre-fill the period the page is showing (falls back to the current one),
        # and the hours with the member's remaining budget — one-click cash-out.
        # The period only labels the draw; it never changes the LCR used.
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
        remaining = remaining_hours_for_role(support_role)
        if remaining is not None and remaining > 0:
            initial["hours_drawn"] = remaining.quantize(
                Decimal("0.01"), rounding="ROUND_DOWN"
            )
        form = SupportBudgetDrawForm(initial=initial)

    context = {"form": form, "job": support_role.job, "instance": support_role}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/job_support_team_draw.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def user_support_auto_draw(request, email):
    """One-click cash out: fill the viewed period's free hours from the user's
    support budgets, oldest job first.

    Never draws more than the period's free hours or any role's remaining
    budget, so it's safe to click again. Same self/manager gate as the
    allocations page.
    """
    from ..utils import period_for_date, auto_cash_out
    from ..utils.support_budget import fmt_decimal, support_draw_message

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

    if p_start > p_end:
        messages.error(request, "The period end must be on or after its start.")
        created = 0
    elif p_start > timezone.now().date():
        messages.error(request, "Support can't be cashed out for a future period.")
        created = 0
    else:
        draws = auto_cash_out(target, p_start, p_end, created_by=request.user)
        created = len(draws)
        for draw in draws:
            log_system_activity(
                draw.support_role.job,
                support_draw_message(target, draw),
                author=request.user,
            )

    if created:
        messages.success(
            request, "Cashed out {}h across {} {} for {} – {}.".format(
                fmt_decimal(sum(d.hours_drawn for d in draws)),
                created,
                "job" if created == 1 else "jobs",
                p_start,
                p_end,
            )
        )
    elif p_start <= p_end and p_start <= timezone.now().date():
        if free_hours_in_period(target, p_start, p_end) <= 0:
            messages.info(
                request, "No free hours left in this period to cash out."
            )
        else:
            messages.info(request, "No support budget left to cash out.")

    url = reverse("user_code_allocation", kwargs={"email": target.email})
    return HttpResponseRedirect(
        "{}?start_date={}&end_date={}".format(url, p_start, p_end)
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
        from .connected_apps import own_connected_apps

        context["connected_apps"] = own_connected_apps(usr)

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


def _get_schedule_viewable_user(request, email):
    """The user whose calendar is requested, if the requester may see it: the
    same rule as the scheduler / API v1 (view_users_schedule on their unit),
    plus anyone who can manage them (self, (acting) manager, manage_user)."""
    from jobtracker.utils import viewable_schedule_user_pks

    user = get_object_or_404(User, email=email)
    if not (
        user.can_be_managed_by(request.user)
        or user.pk in viewable_schedule_user_pks(request.user)
    ):
        raise PermissionDenied
    return user


@login_required
def user_schedule_timeslots(request, email):
    user = _get_schedule_viewable_user(request, email)
    # Change FullCalendar format to DateTime
    start = clean_fullcalendar_datetime(request.GET.get("start", None))
    end = clean_fullcalendar_datetime(request.GET.get("end", None))
    data = user.get_timeslots(
        start=start,
        end=end,
    )
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["GET", "POST"])
def user_schedule_export(request, email):
    """One person's schedule as the scheduler XLSX (T-11).

    Same visibility rule as their Schedule tab (self, manager, manage_user,
    ``view_users_schedule`` on their unit) - deactivated people included. GET
    returns the date-range modal; POST streams the file. Built for exactly
    this user, not through the scheduler's lenient ``users=`` filter."""
    from datetime import date, datetime, time, timedelta
    from jobtracker.schedule_export import build_scheduler_xlsx, SCHEDULER_EXPORT_MAX_DAYS
    from jobtracker.utils import collect_schedule_slots, scheduler_member_rows

    user = _get_schedule_viewable_user(request, email)

    if request.method == "GET":
        today = timezone.localdate()
        context = {
            "export_user": user,
            "default_start": (today - timedelta(days=30)).isoformat(),
            "default_end": (today + timedelta(days=90)).isoformat(),
            "max_days": SCHEDULER_EXPORT_MAX_DAYS,
        }
        return JsonResponse({
            "html_form": loader.render_to_string(
                "modals/user_schedule_export.html", context, request=request
            )
        })

    try:
        start_date = date.fromisoformat(request.POST.get("start", ""))
        end_date = date.fromisoformat(request.POST.get("end", ""))
    except ValueError:
        start_date = end_date = None
    if not start_date or not end_date or end_date < start_date:
        messages.error(request, "Choose a valid date range to export.")
        return HttpResponseRedirect(reverse("user_profile", kwargs={"email": user.email}))
    if (end_date - start_date).days + 1 > SCHEDULER_EXPORT_MAX_DAYS:
        messages.error(
            request,
            "Export range is limited to {} days.".format(SCHEDULER_EXPORT_MAX_DAYS),
        )
        return HttpResponseRedirect(reverse("user_profile", kwargs={"email": user.email}))

    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date, time.max))
    users_qs = User.objects.filter(pk=user.pk).prefetch_related(
        "unit_memberships",
        "unit_memberships__unit",
        "job_level_history",
        "job_level_history__job_level",
    )
    members = scheduler_member_rows(
        request,
        filtered_users=users_qs,
        start=start,
        end=end,
        use_filter_form=False,
        include_html=False,
    )
    users = {u.pk: u for u in users_qs}
    members = [m for m in members if m["id"] in users]
    dataset = collect_schedule_slots(users_qs, start, end)

    fmt = "%d %b %Y"
    header_rows = [
        ("Person", "{} ({})".format(user.get_full_name(), user.email)),
        ("Date Range", "{} to {}".format(start_date.strftime(fmt), end_date.strftime(fmt))),
        ("Generated", "{} by {}".format(
            timezone.localtime().strftime("%d %b %Y %H:%M"), request.user.get_full_name()
        )),
    ]
    slug = (user.email.split("@")[0] or "user").replace(".", "-")
    return build_scheduler_xlsx(
        members,
        users,
        dataset,
        start_date,
        end_date,
        filename="schedule-{}-{}-to-{}".format(
            slug, start_date.isoformat(), end_date.isoformat()
        ),
        title="Schedule — {} — {} to {}".format(
            user.get_full_name() or user.email,
            start_date.strftime(fmt),
            end_date.strftime(fmt),
        ),
        header_rows=header_rows,
    )


@login_required
def user_schedule_holidays(request, email):
    user = _get_schedule_viewable_user(request, email)
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
