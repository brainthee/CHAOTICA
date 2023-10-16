from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import Service
from ..forms import ServiceForm
import logging


logger = logging.getLogger(__name__)

class ServiceBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Service
    fields = '__all__'
    permission_required = 'jobtracker.view_service'
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
            return reverse_lazy('service_detail', kwargs={'slug': slug})
        else:
            return reverse_lazy('service_list')

class ServiceListView(ServiceBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

class ServiceDetailView(ServiceBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = 'jobtracker.view_service'
    accept_global_perms = True
    return_403 = True

class ServiceCreateView(ServiceBaseView, PermissionRequiredMixin, CreateView):
    form_class = ServiceForm
    fields = None

    permission_required = 'jobtracker.add_service'
    accept_global_perms = True
    permission_object = Service
    return_403 = True

class ServiceUpdateView(ServiceBaseView, PermissionRequiredMixin, UpdateView):
    form_class = ServiceForm
    fields = None

    permission_required = 'jobtracker.change_service'
    accept_global_perms = True
    return_403 = True

class ServiceDeleteView(ServiceBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = 'jobtracker.delete_service'
    accept_global_perms = True
    return_403 = True
    