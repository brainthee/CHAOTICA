from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import Team, TeamMember
from guardian.decorators import permission_required_or_403
from ..forms import TeamForm, TeamMemberForm, AddTeamMemberForm
from django.http import HttpResponseBadRequest, JsonResponse
from django.template import loader
import logging, datetime, json
from django.contrib import messages


logger = logging.getLogger(__name__)


class TeamBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Team
    fields = "__all__"
    permission_required = "jobtracker.view_team"
    accept_global_perms = True
    return_403 = True
    success_url = reverse_lazy("team_list")

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("team_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("team_list")


class TeamListView(TeamBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


class TeamDetailView(TeamBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = "jobtracker.view_team"
    accept_global_perms = True
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(TeamDetailView, self).get_context_data(**kwargs)

        date_range_raw = self.request.GET.get("dateRange", "")
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
            context["start_date"] = self.request.GET.get(
                "start_date",
                (timezone.now() - datetime.timedelta(days=30)).date(),
            )
            context["end_date"] = self.request.GET.get(
                "end_date", timezone.now().date()
            )
        
        context["stats"] = self.get_object().get_stats(
            context["start_date"], context["end_date"]
        )
        context["stats_json"] = json.dumps(context["stats"], indent=4, default=str)

        return context


class TeamCreateView(TeamBaseView, PermissionRequiredMixin, CreateView):
    form_class = TeamForm
    fields = None
    permission_required = "jobtracker.add_team"
    accept_global_perms = True
    permission_object = Team
    return_403 = True


class TeamUpdateView(TeamBaseView, PermissionRequiredMixin, UpdateView):
    form_class = TeamForm
    fields = None
    permission_required = "jobtracker.change_team"
    accept_global_perms = True
    return_403 = True


class TeamDeleteView(TeamBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = "jobtracker.delete_team"
    accept_global_perms = True
    return_403 = True


@permission_required_or_403(
    "jobtracker.change_team", (Team, "slug", "slug")
)
def teammember_add(request, slug):
    data = dict()
    team = get_object_or_404(Team, slug=slug)

    data["form_is_valid"] = False

    if request.method == "POST":
        form = AddTeamMemberForm(request.POST, team=team)
        if form.is_valid():
            membership = form.save(commit=False)
            # lets check if they already exist...
            if TeamMember.objects.filter(user=membership.user, team=team, left_at__isnull=True,).exists():
                # Already a member - refuse it...
                form.add_error("user", "User is already a member")
                data["form_is_valid"] = False
            else:
                membership.team = team
                membership.joined_at = timezone.now()
                membership.save()
                data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = AddTeamMemberForm(team=team)

    context = {"team": team, "form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/teammember_form.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403(
    "jobtracker.change_team", (Team, "slug", "slug")
)
def teammember_change(request, slug, member_pk):
    data = dict()
    team = get_object_or_404(Team, slug=slug)
    membership = get_object_or_404(TeamMember, team=team, pk=member_pk)
    data["form_is_valid"] = False

    if request.method == "POST":
        form = TeamMemberForm(request.POST, team=team, instance=membership)
        if form.is_valid():
            membership = form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        form = TeamMemberForm(team=team, instance=membership)

    context = {"team": team, "membership": membership, "form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/teammember_form.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403(
    "jobtracker.change_team", (Team, "slug", "slug")
)
def teammember_remove(request, slug, member_pk):
    data = dict()
    team = get_object_or_404(Team, slug=slug)
    membership = get_object_or_404(TeamMember, team=team, pk=member_pk)
    data["form_is_valid"] = False
    if request.method == "POST":
        membership.delete()
        data["form_is_valid"] = True
        
    context = {"team": team, "membership": membership}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/teammember_remove.html", context, request=request
    )
    return JsonResponse(data)