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
import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages 
from django.apps import apps
import json


logger = logging.getLogger(__name__)


@login_required
def run_tasks(request):
    """A view that manually runs tasks normally run in the background.

    Args:
        request (HttpRequest): The request

    Returns:
        HttpResponse: A redirect
    """
    task_progress_job_workflows(request)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

@login_required
def view_scheduler(request):
    context = {}
    template = loader.get_template('scheduler.html')
    context = {**context, **pageDefaults(request)}
    return HttpResponse(template.render(context, request))



@login_required
def view_stats(request):
    context = {}
    template = loader.get_template('stats.html')
    context = {**context, **pageDefaults(request)}
    return HttpResponse(template.render(context, request))
