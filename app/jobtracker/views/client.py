from django.shortcuts import get_object_or_404
from guardian.shortcuts import get_objects_for_user
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView, pageDefaults
from chaotica_utils.utils import *
from ..models import *
from ..forms import *
from ..tasks import *
import logging

logger = logging.getLogger(__name__)


class ClientBaseView(ChaoticaBaseView):
    model = Client
    fields = '__all__'

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

    def get_context_data(self, **kwargs):
        context = super(ClientDetailView, self).get_context_data(**kwargs)
        # get a list of jobs we're allowed to view...
        myJobs = get_objects_for_user(self.request.user, 'jobtracker.view_job', context['client'].jobs.all())
        context['allowedJobs'] = myJobs
        return context

class ClientCreateView(ClientBaseView, CreateView):
    form_class = ClientForm
    fields = None

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

class ClientUpdateView(ClientBaseView, UpdateView):
    form_class = ClientForm
    fields = None

class ClientDeleteView(ClientBaseView, DeleteView):
    """View to delete a job"""
    

class ClientContactBaseView(ChaoticaBaseView):
    model = Contact
    fields = '__all__'

    def get_context_data(self, **kwargs):
        context = super(ClientContactBaseView, self).get_context_data(**kwargs)
        if 'slug' in self.kwargs:
            context['client'] = get_object_or_404(Client, slug=self.kwargs['slug'])
        return context

    def get_success_url(self):
        slug = None
        pk = None
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
        if 'pk' in self.kwargs:
            pk = self.kwargs['pk']
        
        if slug and pk:
            return reverse_lazy('client_contact_detail', kwargs={'slug': slug, 'pk': pk})
        elif slug:
            return reverse_lazy('client_detail', kwargs={'slug': slug})            
        else:
            return reverse_lazy('client_list')

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

    def form_valid(self, form):
        form.instance.company = Client.objects.get(slug=self.kwargs['slug'])
        return super().form_valid(form)

class ClientContactUpdateView(ClientContactBaseView, UpdateView):
    form_class = ClientContactForm
    fields = None

class ClientContactDeleteView(ClientContactBaseView, DeleteView):
    """View to delete a job"""