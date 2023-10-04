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
from chaotica_utils.utils import *
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


class SkillBaseView(ChaoticaBaseView):
    model = Skill
    fields = '__all__'
    success_url = reverse_lazy('skill_list')

    def get_context_data(self, **kwargs):
        context = super(SkillBaseView, self).get_context_data(**kwargs)
        # Get categories
        context['categories'] = SkillCategory.objects.all()
        return context

class SkillListView(SkillBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

class SkillDetailView(SkillBaseView, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

class SkillCreateView(SkillBaseView, CreateView):
    form_class = SkillForm
    fields = None

    def get_context_data(self, **kwargs):
        context = super(SkillCreateView, self).get_context_data(**kwargs)
        # Get categories
        context['category'] = SkillCategory.objects.get(slug=self.kwargs['catSlug'])     
        return context

    def form_valid(self, form):
        form.instance.category = SkillCategory.objects.get(slug=self.kwargs['catSlug'])        
        return super(SkillCreateView, self).form_valid(form)

class SkillUpdateView(SkillBaseView, UpdateView):
    form_class = SkillForm
    fields = None

class SkillDeleteView(SkillBaseView, DeleteView):
    """View to delete a job"""
    

class SkillCatBaseView(ChaoticaBaseView):
    model = SkillCategory
    fields = '__all__'
    success_url = reverse_lazy('skill_list')

class SkillCatCreateView(SkillCatBaseView, CreateView):
    form_class = SkillCatForm
    fields = None

class SkillCatUpdateView(SkillCatBaseView, UpdateView):
    form_class = SkillCatForm
    fields = None

class SkillCatDeleteView(SkillCatBaseView, DeleteView):
    """View to delete a job"""