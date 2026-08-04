from chaotica_utils.mixins import (
    SecurePermissionRequiredMixin as PermissionRequiredMixin,
)
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from chaotica_utils.views import ChaoticaBaseView, log_system_activity
from chaotica_utils.decorators import permission_required_or_403
from chaotica_utils.models import User
from django.contrib.auth.decorators import login_required
from django.template import loader
from django.http import JsonResponse
from ..models import Project, TimeSlot
from ..forms import ProjectForm
from ..utils import get_scheduler_slots, get_scheduler_members
import json
import logging

logger = logging.getLogger(__name__)


def _project_scheduled_users(project):
    return User.objects.filter(
        pk__in=TimeSlot.objects.filter(project=project).values("user")
    )


@permission_required_or_403("jobtracker.view_project")
def view_project_schedule_slots(request, slug):
    """Read-only vis-timeline slots feed scoped to a single project's timeslots."""
    project = get_object_or_404(Project, slug=slug)
    return get_scheduler_slots(
        request,
        filtered_users=_project_scheduled_users(project),
        use_filter_form=False,
        scope_projects=[project],
        hard_scope=True,
    )


@permission_required_or_403("jobtracker.view_project")
def view_project_schedule_members(request, slug):
    """Members (groups) feed for a project's read-only schedule tab."""
    project = get_object_or_404(Project, slug=slug)
    return get_scheduler_members(
        request,
        filtered_users=_project_scheduled_users(project),
        use_filter_form=False,
        role_job=None,
    )


@login_required
@permission_required_or_403("jobtracker.view_project")
def project_stats_partial(request, slug):
    """Lazily-loaded stats tab for the project detail page.

    Mirrors ``orgunit_stats_partial`` / ``team_stats_partial`` — computes the
    day-based stats once and renders them into the partial, also emitting the
    serialised ``stats_json`` for the echarts / raw-data view.
    """
    project = get_object_or_404(Project, slug=slug)
    stats = project.get_stats()
    context = {
        "project": project,
        "stats": stats,
        "stats_json": json.dumps(stats, indent=4, default=str),
    }
    html = loader.render_to_string(
        "partials/project/project_stats.html", context, request=request
    )
    # The Project detail "Team" tab reuses the same per-member block, so return
    # it separately — the page fetches this endpoint once and fills both panes.
    members_html = loader.render_to_string(
        "partials/project/project_members_table.html", context, request=request
    )
    return JsonResponse({"html": html, "members_html": members_html})


class ProjectBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Project
    fields = "__all__"
    permission_required = "jobtracker.view_project"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("project_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("project_list")


class ProjectListView(ProjectBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


class ProjectDetailView(ProjectBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = "jobtracker.view_project"
    accept_global_perms = True
    return_403 = True
    # Team + Stats tabs are lazily loaded (see project_stats_partial), so the
    # base detail page stays lightweight — no eager stats/member computation.


class ProjectCreateView(ProjectBaseView, PermissionRequiredMixin, CreateView):
    form_class = ProjectForm
    fields = None

    permission_required = "jobtracker.add_project"
    accept_global_perms = True
    permission_object = Project
    return_403 = True

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_system_activity(
            self.object, "Project created", author=self.request.user
        )
        return response


class ProjectUpdateView(ProjectBaseView, PermissionRequiredMixin, UpdateView):
    form_class = ProjectForm
    fields = None

    permission_required = "jobtracker.change_project"
    accept_global_perms = True
    return_403 = True

    def form_valid(self, form):
        response = super().form_valid(form)
        log_system_activity(
            self.object, "Project updated", author=self.request.user
        )
        return response


class ProjectDeleteView(ProjectBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = "jobtracker.delete_project"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        return reverse_lazy("project_list")
