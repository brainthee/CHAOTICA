from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import Certification
from ..forms import CertificationForm
import logging


logger = logging.getLogger(__name__)

class CertificationBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Certification
    fields = '__all__'
    permission_required = 'jobtracker.view_certification'
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
            return reverse_lazy('certification_detail', kwargs={'slug': slug})
        else:
            return reverse_lazy('certification_list')

class CertificationListView(CertificationBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

class CertificationDetailView(CertificationBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = 'jobtracker.view_certification'
    accept_global_perms = True
    return_403 = True

class CertificationCreateView(CertificationBaseView, PermissionRequiredMixin, CreateView):
    form_class = CertificationForm
    fields = None

    permission_required = 'jobtracker.add_certification'
    accept_global_perms = True
    permission_object = Certification
    return_403 = True

class CertificationUpdateView(CertificationBaseView, PermissionRequiredMixin, UpdateView):
    form_class = CertificationForm
    fields = None

    permission_required = 'jobtracker.change_certification'
    accept_global_perms = True
    return_403 = True

class CertificationDeleteView(CertificationBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = 'jobtracker.delete_certification'
    accept_global_perms = True
    return_403 = True
    