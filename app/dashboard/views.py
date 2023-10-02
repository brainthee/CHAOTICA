from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse,HttpResponseRedirect, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden, HttpResponseNotFound
from django.template import loader, Template as tmpl, Context
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages 
import logging
from django.utils.safestring import mark_safe
from datetime import datetime
from jobtracker.models import *
from chaotica_utils.models import *
from chaotica_utils.views import pageDefaults

logger = logging.getLogger(__name__)

@login_required
def index(request):
    context = {}
    template = loader.get_template('dashboard_index.html')
    context['pendingScoping'] = Job.objects.filter(status=JobStatuses.PENDING_SCOPE)
    context['scopesToSignoff'] = Job.objects.filter(status=JobStatuses.PENDING_SCOPING_SIGNOFF)
    if request.user.is_people_manager():
        context['leaveToReview'] = LeaveRequest.objects.filter(Q(user__manager=request.user) | Q(user__acting_manager=request.user))
    context = {**context, **pageDefaults(request)}
    return HttpResponse(template.render(context, request))