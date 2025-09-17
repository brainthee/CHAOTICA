from guardian.mixins import PermissionRequiredMixin
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import Project
from ..forms import ProjectForm
import logging

logger = logging.getLogger(__name__)


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
