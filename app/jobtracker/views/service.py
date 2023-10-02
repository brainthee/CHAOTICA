from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse,HttpResponseRedirect, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden, HttpResponseNotFound
from django.template import loader, Template as tmpl, Context
from guardian.decorators import permission_required_or_403
from guardian.core import ObjectPermissionChecker
from guardian.mixins import PermissionListMixin, PermissionRequiredMixin
from django.views import View
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView, pageDefaults
from chaotica_utils.utils import SendUserNotification
from ..models import *
from ..forms import *
from ..tasks import *
from .helpers import *
import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages 
from django.apps import apps
import json


logger = logging.getLogger(__name__)

class ServiceBaseView(ChaoticaBaseView):
    model = Service
    fields = '__all__'

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

class ServiceDetailView(ServiceBaseView, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

class ServiceCreateView(ServiceBaseView, CreateView):
    form_class = ServiceForm
    fields = None

class ServiceUpdateView(ServiceBaseView, UpdateView):
    form_class = ServiceForm
    fields = None

class ServiceDeleteView(ServiceBaseView, DeleteView):
    """View to delete a job"""
    