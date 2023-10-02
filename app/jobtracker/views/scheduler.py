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
def view_scheduler_slots(request):
    data = []
    orgUnits = get_objects_for_user(request.user, 'jobtracker.view_users_schedule')
    for orgUnit in orgUnits:
        scheduledUsers = orgUnit.get_activeMembers()
        for user in scheduledUsers:
            data = data + user.get_timeslots(
                start=request.GET.get('start', None),
                end=request.GET.get('end', None),
                )
    return JsonResponse(data, safe=False)


@login_required
def view_scheduler_members(request):
    data = []

    today = timezone.now().today()
    start_of_week = today - timedelta(days = today.weekday())
    end_of_week = start_of_week + timedelta(days = 6)
    start = request.GET.get('start', start_of_week)
    end = request.GET.get('end', end_of_week)

    # get the org unit's we're in that we have perms for...
    orgUnits = get_objects_for_user(request.user, 'jobtracker.view_users_schedule')
    for orgUnit in orgUnits:
        scheduledUsers = orgUnit.get_activeMembers()
        for user in scheduledUsers:
            userTitle = str(user)
            data.append({
                "id": user.pk,
                "title": userTitle,
                "businessHours": {
                    "startTime": orgUnit.businessHours_startTime,
                    "endTime": orgUnit.businessHours_endTime,
                    "daysOfWeek": orgUnit.businessHours_days,
                }
            })
    return JsonResponse(data, safe=False)

@login_required
def view_own_schedule_timeslots(request):
    data = request.user.get_timeslots(
        start=request.GET.get('start', None),
        end=request.GET.get('end', None),
        )
    return JsonResponse(data, safe=False)


class SlotDeleteView(ChaoticaBaseView, DeleteView):
    """View to delete a slot"""
    model = TimeSlot  
    template_name = "jobtracker/modals/job_slot_delete.html"  

    def get_success_url(self):
        slug = self.kwargs['slug']
        return reverse_lazy('job_schedule', kwargs={'slug': slug})

    def get_context_data(self, **kwargs):
        context = super(SlotDeleteView, self).get_context_data(**kwargs)
        if 'slug' in self.kwargs:
            context['job'] = get_object_or_404(Job, slug=self.kwargs['slug'])
        return context