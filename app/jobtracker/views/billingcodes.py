from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import BillingCode
from ..forms import BillingCodeForm
import logging


logger = logging.getLogger(__name__)

class BillingCodeBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = BillingCode
    fields = '__all__'
    permission_required = 'jobtracker.view_billingcode'
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
            return reverse_lazy('billingcode_detail', kwargs={'slug': slug})
        else:
            return reverse_lazy('billingcode_list')

class BillingCodeListView(BillingCodeBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

class BillingCodeDetailView(BillingCodeBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = 'jobtracker.view_billingcode'
    accept_global_perms = True
    return_403 = True
    slug_url_kwarg = "code"
    slug_field = "code"

class BillingCodeCreateView(BillingCodeBaseView, PermissionRequiredMixin, CreateView):
    form_class = BillingCodeForm
    fields = None

    permission_required = 'jobtracker.add_billingcode'
    accept_global_perms = True
    permission_object = BillingCode
    return_403 = True

class BillingCodeUpdateView(BillingCodeBaseView, PermissionRequiredMixin, UpdateView):
    form_class = BillingCodeForm
    fields = None

    permission_required = 'jobtracker.change_billingcode'
    accept_global_perms = True
    return_403 = True
    slug_url_kwarg = "code"
    slug_field = "code"

class BillingCodeDeleteView(BillingCodeBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = 'jobtracker.delete_billingcode'
    accept_global_perms = True
    return_403 = True
    slug_url_kwarg = "code"
    slug_field = "code"
    