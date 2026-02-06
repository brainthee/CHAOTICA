from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.utils import get_week
from ..models import Team, TeamMember, TimeSlot
from ..enums import PhaseStatuses
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

        # Debrief tab - only for team owners and superusers
        team = self.get_object()
        user = self.request.user
        is_team_owner = user.is_superuser or team.owners.filter(pk=user.pk).exists()
        context["is_team_owner"] = is_team_owner

        if is_team_owner:
            week_offset = self.request.GET.get('week', '0')
            try:
                week_offset = int(week_offset)
            except (ValueError, TypeError):
                week_offset = 0
            context.update(self._get_debrief_context(team, week_offset))

        return context

    def _get_debrief_context(self, team, week_offset=0):
        this_week = get_week()
        week_start = this_week['start'] + datetime.timedelta(weeks=week_offset)
        week_end = this_week['end'] + datetime.timedelta(weeks=week_offset)
        week_friday = week_start + datetime.timedelta(days=4)

        next_week_start = week_start + datetime.timedelta(days=7)
        next_week_end = week_end + datetime.timedelta(days=7)

        members = team.get_activeMembers().order_by('first_name', 'last_name')

        members_data = []
        for member in members:
            this_week_slots = TimeSlot.objects.filter(
                user=member,
                start__date__lte=week_friday.date() if hasattr(week_friday, 'date') else week_friday,
                end__date__gte=week_start.date() if hasattr(week_start, 'date') else week_start,
            ).select_related(
                'slot_type', 'phase', 'phase__job', 'phase__job__client', 'phase__service',
            ).order_by('start')

            # Build Mon-Fri daily breakdown
            daily_slots = {}
            for day_offset in range(5):
                day_date = (week_start + datetime.timedelta(days=day_offset))
                if hasattr(day_date, 'date'):
                    day_date = day_date.date()
                daily_slots[day_offset] = {
                    'date': day_date,
                    'slots': [],
                }

            for slot in this_week_slots:
                slot_start_date = slot.start.date() if hasattr(slot.start, 'date') else slot.start
                slot_end_date = slot.end.date() if hasattr(slot.end, 'date') else slot.end
                for day_offset in range(5):
                    day_date = (week_start + datetime.timedelta(days=day_offset))
                    if hasattr(day_date, 'date'):
                        day_date = day_date.date()
                    if slot_start_date <= day_date <= slot_end_date:
                        daily_slots[day_offset]['slots'].append(slot)

            # Phases this week (distinct)
            phases_this_week = []
            seen_phase_pks = set()
            for slot in this_week_slots:
                if slot.phase and slot.phase.pk not in seen_phase_pks:
                    seen_phase_pks.add(slot.phase.pk)
                    role_display = slot.get_deliveryRole_display()
                    phases_this_week.append({
                        'phase': slot.phase,
                        'role': role_display,
                    })

            # Next week pre-checks warnings
            next_week_slots = TimeSlot.objects.filter(
                user=member,
                start__date__lte=next_week_end.date() if hasattr(next_week_end, 'date') else next_week_end,
                end__date__gte=next_week_start.date() if hasattr(next_week_start, 'date') else next_week_start,
                phase__isnull=False,
            ).select_related(
                'phase', 'phase__job', 'phase__job__client',
            )

            next_week_warnings = []
            seen_warning_pks = set()
            for slot in next_week_slots:
                phase = slot.phase
                if phase.pk not in seen_warning_pks and phase.status < PhaseStatuses.READY_TO_BEGIN:
                    seen_warning_pks.add(phase.pk)
                    next_week_warnings.append(phase)

            members_data.append({
                'user': member,
                'daily_slots': daily_slots,
                'phases_this_week': phases_this_week,
                'next_week_warnings': next_week_warnings,
            })

        # Build day headers
        day_headers = []
        for day_offset in range(5):
            day_date = week_start + datetime.timedelta(days=day_offset)
            if hasattr(day_date, 'date'):
                day_date = day_date.date()
            day_headers.append(day_date)

        return {
            'members_data': members_data,
            'week_start': week_start.date() if hasattr(week_start, 'date') else week_start,
            'week_friday': week_friday.date() if hasattr(week_friday, 'date') else week_friday,
            'day_headers': day_headers,
            'debrief_week_offset': str(week_offset),
            'debrief_prev_week': str(week_offset - 1),
            'debrief_next_week': str(week_offset + 1),
        }


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