from guardian.mixins import PermissionRequiredMixin
from django.shortcuts import get_object_or_404
from guardian.shortcuts import get_objects_for_user
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from ..models import Client, Contact, OrganisationalUnit
from ..forms import ClientForm, ClientContactForm
import logging

logger = logging.getLogger(__name__)


class ClientBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Client
    fields = '__all__'
    permission_required = 'jobtracker.view_client'
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
            return reverse_lazy('client_detail', kwargs={'slug': slug})
        else:
            return reverse_lazy('client_list')

class ClientListView(ClientBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

class ClientDetailView(ClientBaseView, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = 'jobtracker.view_client'

    def get_context_data(self, **kwargs):
        context = super(ClientDetailView, self).get_context_data(**kwargs)
        # get a list of jobs we're allowed to view...
        my_jobs = get_objects_for_user(self.request.user, 'jobtracker.view_job', context['client'].jobs.all())
        context['allowedJobs'] = my_jobs
        return context

class ClientCreateView(ClientBaseView, CreateView):
    form_class = ClientForm
    fields = None

    permission_required = 'jobtracker.add_client'
    accept_global_perms = True
    permission_object = OrganisationalUnit

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

class ClientUpdateView(ClientBaseView, UpdateView):
    form_class = ClientForm
    fields = None

    permission_required = 'jobtracker.change_client'

class ClientDeleteView(ClientBaseView, DeleteView):
    """View to delete a job"""
    permission_required = 'jobtracker.delete_client'
    



class ClientContactBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Contact
    fields = '__all__'
    client_slug = None
    permission_required = 'jobtracker.view_contact'
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        pk = None
        if 'pk' in self.kwargs:
            pk = self.kwargs['pk']
        if 'client_slug' in self.kwargs:
            client_slug = self.kwargs['client_slug']
        
        if client_slug and pk:
            return reverse_lazy('client_contact_detail', kwargs={'client_slug': client_slug, 'pk': pk})
        elif client_slug:
            return reverse_lazy('client_detail', kwargs={'slug': client_slug})            
        else:
            return reverse_lazy('client_list')

    def get_context_data(self, **kwargs):
        context = super(ClientContactBaseView, self).get_context_data(**kwargs)
        if 'client_slug' in self.kwargs:
            context['client'] = get_object_or_404(Client, slug=self.kwargs['client_slug'])
        return context

class ClientContactListView(ClientContactBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

class ClientContactDetailView(ClientContactBaseView, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

class ClientContactCreateView(ClientContactBaseView, CreateView):
    form_class = ClientContactForm
    fields = None
    permission_object = None
    permission_required = 'jobtracker.add_contact'
    # permission_required = None

    def form_valid(self, form):
        form.instance.company = Client.objects.get(slug=self.kwargs['client_slug'])
        form.instance.save()
        log_system_activity(form.instance, "Created")
        return super(ClientContactCreateView, self).form_valid(form)

    def get_form_kwargs(self):
        kwargs = super(ClientContactCreateView, self).get_form_kwargs()
        if 'client_slug' in self.kwargs:
            kwargs['client'] = get_object_or_404(Client, slug=self.kwargs['client_slug'])
        return kwargs

class ClientContactUpdateView(ClientContactBaseView, UpdateView):
    form_class = ClientContactForm
    fields = None

class ClientContactDeleteView(ClientContactBaseView, DeleteView):
    """View to delete a job"""