from chaotica_utils.mixins import (
    SecurePermissionRequiredMixin as PermissionRequiredMixin,
)
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.decorators import permission_required_or_403
from chaotica_utils.models import User
from ..models import Project, TimeSlot
from ..forms import ProjectForm
from ..utils import get_scheduler_slots, get_scheduler_members
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["scheduled_users"] = _project_scheduled_users(self.object).order_by(
            "first_name", "last_name"
        )
        return ctx


class ProjectCreateView(ProjectBaseView, PermissionRequiredMixin, CreateView):
    form_class = ProjectForm
    fields = None

    permission_required = "jobtracker.add_project"
    accept_global_perms = True
    permission_object = Project
    return_403 = True

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ProjectUpdateView(ProjectBaseView, PermissionRequiredMixin, UpdateView):
    form_class = ProjectForm
    fields = None

    permission_required = "jobtracker.change_project"
    accept_global_perms = True
    return_403 = True


class ProjectDeleteView(ProjectBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = "jobtracker.delete_project"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        return reverse_lazy("project_list")
