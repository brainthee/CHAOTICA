from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponseRedirect, HttpResponseBadRequest, JsonResponse
from django.template import loader
from django.views import View
from django.db.models import Q, CharField, ExpressionWrapper
from django.db.models import Value as V
from guardian.mixins import PermissionRequiredMixin
from django.db.models.functions import Concat
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from ..models import Job, Project, WorkflowTask
from ..forms import ProjectForm
from ..enums import FeedbackType, PhaseStatuses, TimeSlotDeliveryRole, JobStatuses
from .helpers import _process_assign_user
from chaotica_utils.tasks import task_send_notifications
from chaotica_utils.utils import AppNotification
from chaotica_utils.enums import NotificationTypes
import logging
from dal import autocomplete
from ..decorators import unit_permission_required_or_403
from ..mixins import UnitPermissionRequiredMixin
from chaotica_utils.utils import (
    clean_date,
)

logger = logging.getLogger(__name__)


class ProjectAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return Project.objects.none()
        # qs = Phase.objects.phases_with_unit_permission(
        #     self.request.user, "jobtracker.can_view_jobs"
        # )
        qs = Project.objects.all()
        if self.q:
            qs = qs.filter(
                Q(title__icontains=self.q)
            )
        return qs

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
