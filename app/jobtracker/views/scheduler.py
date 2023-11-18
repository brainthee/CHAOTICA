from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.template import loader
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import page_defaults
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.models import User
from guardian.shortcuts import get_objects_for_user
from ..models import Job, TimeSlot, UserSkill, Phase
from ..forms import NonDeliveryTimeSlotModalForm, SchedulerFilter, ChangeTimeSlotDateModalForm, DeliveryChangeTimeSlotModalForm
from ..enums import UserSkillRatings
import logging
from django.contrib.auth.decorators import login_required


logger = logging.getLogger(__name__)


@login_required
def view_scheduler(request):
    context = {}
    template = loader.get_template('scheduler.html')
    context = {**context, **page_defaults(request)}
    context['filterForm'] = SchedulerFilter(request.GET)
    return HttpResponse(template.render(context, request))


def _filter_users_on_query(request):
    filterForm = SchedulerFilter(request.GET)
    users_pk = []
    for org_unit in get_objects_for_user(request.user, 'jobtracker.view_users_schedule'):
        for user in org_unit.get_activeMembers():
            if user.pk not in users_pk:
                users_pk.append(user.pk)

    users = User.objects.filter(pk__in=users_pk)

    if filterForm.is_valid():
        # Now lets apply the filters from the query...
        ## Filter users
        users_q = filterForm.cleaned_data.get('users')
        if users_q:
            users = users.filter(pk__in=users_q)

        ## Filter on skills
        skills_specialist = filterForm.cleaned_data.get('skills_specialist')
        if skills_specialist:
            users = users.filter(skills__in=UserSkill.objects.filter(skill__in=skills_specialist, rating=UserSkillRatings.SPECIALIST))

        skills_can_do_alone = filterForm.cleaned_data.get('skills_can_do_alone')
        if skills_can_do_alone:
            users = users.filter(skills__in=UserSkill.objects.filter(skill__in=skills_can_do_alone, rating=UserSkillRatings.CAN_DO_ALONE))

        skills_can_do_support = filterForm.cleaned_data.get('skills_can_do_support')
        if skills_can_do_support:
            users = users.filter(skills__in=UserSkill.objects.filter(skill__in=skills_can_do_support, rating=UserSkillRatings.CAN_DO_WITH_SUPPORT))
        
        # Filter on service
        # This is a bit mind bending. Of the service(s) selected, each will have some desired/needed skills
        # We then need to select the users based off containing a skill in either desired or needed..
        services = filterForm.cleaned_data.get('services')
        for service in services:
            users = users.filter(pk__in=service.users_can_conduct())

    return users


@login_required
def view_scheduler_slots(request):
    data = []
    scheduled_users = _filter_users_on_query(request)
    for user in scheduled_users:
        data = data + user.get_timeslots(
            start=request.GET.get('start', None),
            end=request.GET.get('end', None),)
        data = data + user.get_holidays(
            start=request.GET.get('start', None),
            end=request.GET.get('end', None),)
    return JsonResponse(data, safe=False)


@login_required
def view_scheduler_members(request):
    data = []
    scheduled_users = _filter_users_on_query(request)
    for user in scheduled_users:
        user_title = str(user)
        main_org = user.unit_memberships.first()
        data.append({
            "id": user.pk,
            "title": user_title,
            "businessHours": {
                "startTime": main_org.unit.businessHours_startTime,
                "endTime": main_org.unit.businessHours_endTime,
                "daysOfWeek": main_org.unit.businessHours_days,
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

@login_required
def view_schedule_holidays(request):
    data = request.user.get_holidays(
        start=request.GET.get('start', None),
        end=request.GET.get('end', None),
        )
    return JsonResponse(data, safe=False)


# @permission_required('jobtracker.change_schedule', (Job, 'slug', 'slug'))
def change_scheduler_slot_date(request, pk=None):
    if not pk:
        # We only do this because we want to generate the URL in JS land
        return HttpResponseBadRequest()
    slot = get_object_or_404(TimeSlot, pk=pk)
    data = dict()
    if request.method == "POST":
        form = ChangeTimeSlotDateModalForm(request.POST, instance=slot)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
            data['form_errors'] = form.errors
    else:
        # Send the modal
        form = ChangeTimeSlotDateModalForm(instance=slot)

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/job_slot.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


# @permission_required('jobtracker.change_schedule', (Job, 'slug', 'slug'))
def change_scheduler_slot(request, pk=None):
    if not pk:
        # We only do this because we want to generate the URL in JS land
        return HttpResponseBadRequest()
    slot = get_object_or_404(TimeSlot, pk=pk)
    data = dict()
    if request.method == "POST":
        form = NonDeliveryTimeSlotModalForm(request.POST, instance=slot)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
            data['form_errors'] = form.errors
    else:
        # Send the modal
        form = NonDeliveryTimeSlotModalForm(instance=slot)

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/job_slot.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


@login_required
def create_scheduler_internal_slot(request):
    data = dict()
    start = request.GET.get('start', None)
    end = request.GET.get('end', None)
    resource_id = request.GET.get('resource_id', None)

    if request.method == 'POST':
        form = NonDeliveryTimeSlotModalForm(request.POST, start=start, end=end, resource_id=resource_id)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = NonDeliveryTimeSlotModalForm(start=start, end=end, resource_id=resource_id)

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/job_slot_create.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


@login_required
def create_scheduler_phase_slot(request):
    data = dict()
    start = request.GET.get('start', None)
    end = request.GET.get('end', None)
    resource_id = request.GET.get('resource_id', None)
    if resource_id:
        user = get_object_or_404(User, pk=resource_id)
    else:
        user = None
    phase_id = request.GET.get('phase_id', None)
    if phase_id:
        phase = get_object_or_404(Phase, pk=phase_id)
    else:
        phase = None

    if request.method == 'POST':
        form = DeliveryChangeTimeSlotModalForm(request.POST, start=start, end=end, user=user, phase=phase)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = DeliveryChangeTimeSlotModalForm(start=start, end=end, user=user, phase=phase)

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/job_slot_create.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


@login_required
def create_scheduler_comment(request):
    data = dict()
    start = request.GET.get('start', None)
    end = request.GET.get('end', None)
    resource_id = request.GET.get('resource_id', None)

    if request.method == 'POST':
        form = NonDeliveryTimeSlotModalForm(request.POST, start=start, end=end, resource_id=resource_id)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = NonDeliveryTimeSlotModalForm(start=start, end=end, resource_id=resource_id)

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/job_slot_create.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


@login_required
def clear_scheduler_range(request):
    data = dict()
    start = request.GET.get('start', None)
    end = request.GET.get('end', None)
    resource_id = request.GET.get('resource_id', None)

    if request.method == 'POST':
        form = NonDeliveryTimeSlotModalForm(request.POST, start=start, end=end, resource_id=resource_id)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = NonDeliveryTimeSlotModalForm(start=start, end=end, resource_id=resource_id)

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/job_slot_create.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


class SlotDeleteView(ChaoticaBaseView, DeleteView):
    """View to delete a slot"""
    model = TimeSlot  
    template_name = "jobtracker/modals/job_slot_delete.html"  

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs['slug']
            return reverse_lazy('job_schedule', kwargs={'slug': slug})
        else:
            return reverse_lazy('view_scheduler')

    def get_context_data(self, **kwargs):
        context = super(SlotDeleteView, self).get_context_data(**kwargs)
        if 'slug' in self.kwargs:
            context['job'] = get_object_or_404(Job, slug=self.kwargs['slug'])
        return context