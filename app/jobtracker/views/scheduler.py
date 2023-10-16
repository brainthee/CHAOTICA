from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from guardian.shortcuts import get_objects_for_user
from ..models import Job, TimeSlot
import logging
from django.contrib.auth.decorators import login_required


logger = logging.getLogger(__name__)



@login_required
def view_scheduler_slots(request):
    data = []
    for org_unit in get_objects_for_user(request.user, 'jobtracker.view_users_schedule'):
        scheduled_users = org_unit.get_activeMembers()
        for user in scheduled_users:
            data = data + user.get_timeslots(
                start=request.GET.get('start', None),
                end=request.GET.get('end', None),
                )
    return JsonResponse(data, safe=False)


@login_required
def view_scheduler_members(request):
    data = []

    # get the org unit's we're in that we have perms for...
    for org_unit in get_objects_for_user(request.user, 'jobtracker.view_users_schedule'):
        scheduled_users = org_unit.get_activeMembers()
        for user in scheduled_users:
            user_title = str(user)
            data.append({
                "id": user.pk,
                "title": user_title,
                "businessHours": {
                    "startTime": org_unit.businessHours_startTime,
                    "endTime": org_unit.businessHours_endTime,
                    "daysOfWeek": org_unit.businessHours_days,
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