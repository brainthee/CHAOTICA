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
from ..models import User, Language, UserInvitation
from ..utils import (
    ext_reverse,
    clean_fullcalendar_datetime,
    can_manage_user,
)
from .common import ChaoticaBaseGlobalRoleView, page_defaults
from django.contrib.auth.decorators import login_required
from guardian.decorators import permission_required_or_403
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView
from django.contrib import messages
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
        return context


@login_required
@require_safe
def view_own_profile(request):
    # Redirect to public profile
    return HttpResponseRedirect(redirect_to=request.user.get_absolute_url())


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
@require_http_methods(["GET", "POST"])
def update_profile(request, email):
    from jobtracker.models import Skill

    usr = can_manage_user(request.user, email)
    if not usr:
        return HttpResponseForbidden()

    if request.method == "POST":
        form = EditProfileForm(
            request.POST, request.FILES, current_request=request, instance=usr
        )
        if form.is_valid():
            obj = form.save()
            obj.profile_last_updated = timezone.now().today()
            obj.save()
            if "location" in form.changed_data:
                obj.update_latlong()
            usr.refresh_from_db()
    else:
        # Send the modal
        form = EditProfileForm(current_request=request, instance=usr)

    context = {
        "usr": usr,
        "skills": Skill.objects.all().prefetch_related("category").order_by("category", "name"),
        "languages": Language.objects.all(),
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
        # Lets loop through the fields!
        for field in request.POST:
            # get skill..
            try:
                skill = Skill.objects.get(slug=field)
                value = int(request.POST.get(field))
                
                skill, _ = UserSkill.objects.get_or_create(user=usr, skill=skill)
                if skill.rating != value:
                    skill.rating = value
                    skill.last_updated_on = timezone.now()
                    skill.save()
            except:
                # invalid skill!
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
        if u.is_active and state == "deactivate":
            u.is_active = False
            u.save()
            data["form_is_valid"] = True
        elif not u.is_active and state == "activate":
            u.is_active = True
            u.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False

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
