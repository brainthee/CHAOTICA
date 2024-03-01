from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.template import loader
from django.db.models import Q
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import page_defaults
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.models import User
from guardian.shortcuts import get_objects_for_user
from ..models import Job, TimeSlot, UserSkill, Phase, OrganisationalUnitMember
from ..forms import NonDeliveryTimeSlotModalForm, SchedulerFilter, ChangeTimeSlotDateModalForm, DeliveryTimeSlotModalForm
from ..enums import UserSkillRatings
import logging
from django.contrib.auth.decorators import login_required


logger = logging.getLogger(__name__)


@login_required
def view_scheduler(request):
    context = {}
    template = loader.get_template('scheduler.html')
    context = {**context, **page_defaults(request)}
    context['filter_form'] = SchedulerFilter(request.GET)
    return HttpResponse(template.render(context, request))


def _filter_users_on_query(request):
    from pprint import pprint
    filter_form = SchedulerFilter(request.GET)
    # Starting users filter
    users_pk = []
    # This pre-loads which users we can see the schedule of. 
    # It's actually not ideal because if we view a job/phase, 
    # but say we don't have permission to see the schedule of someone - we can't see a complete schedule for that job
    for org_unit in get_objects_for_user(request.user, 'jobtracker.view_users_schedule'):
        for user in org_unit.get_activeMembers():
            if user.pk not in users_pk:
                users_pk.append(user.pk)

    query = Q(is_active=True)
       
    # If we're passed a job/phase ID - filter on that.
    if request.GET.get('job'):
        job = get_object_or_404(Job, pk=int(request.GET.get('job')))
        if request.GET.get('phase'):
            phase = get_object_or_404(Phase, job=job, pk=int(request.GET.get('phase')))
            query.add(Q(pk__in=phase.team()),Q.AND)
        else:
            # get the team for the whole job...
            query.add(Q(pk__in=job.team()),Q.AND)
    else:
        query.add(Q(pk__in=users_pk), Q.AND)

    if filter_form.is_valid():
        # Now lets apply the filters from the query...
        ## Filter users
        users_q = filter_form.cleaned_data.get('users')
        if users_q:
            query.add(Q(pk__in=users_q), Q.AND)

        ## Filter org unit
        org_units = filter_form.cleaned_data.get('org_units')
        if org_units:
            query.add(Q(unit_memberships__in=OrganisationalUnitMember.objects.filter(unit__in=org_units, 
                                            )),Q.AND)

        ## Filter on skills
        skills_specialist = filter_form.cleaned_data.get('skills_specialist')
        if skills_specialist:
            query.add(Q(skills__in=UserSkill.objects.filter(skill__in=skills_specialist, 
                                                            rating=UserSkillRatings.SPECIALIST)),Q.AND)

        skills_can_do_alone = filter_form.cleaned_data.get('skills_can_do_alone')
        if skills_can_do_alone:
            query.add(Q(skills__in=UserSkill.objects.filter(skill__in=skills_can_do_alone, 
                                                            rating=UserSkillRatings.CAN_DO_ALONE)),Q.AND)

        skills_can_do_support = filter_form.cleaned_data.get('skills_can_do_support')
        if skills_can_do_support:
            query.add(Q(skills__in=UserSkill.objects.filter(skill__in=skills_can_do_support, 
                                                            rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)),Q.AND)
        
        # Filter on service
        # This is a bit mind bending. Of the service(s) selected, each will have some desired/needed skills
        # We then need to select the users based off containing a skill in either desired or needed..
        services = filter_form.cleaned_data.get('services')
        for service in services:
            query.add(Q(pk__in=service.users_can_conduct()),Q.AND)


    if request.GET.get('include_user'):
        extra_user = int(request.GET.get('include_user'))
        if extra_user:
            query.add(Q(pk__in=[extra_user,]), Q.OR)

    return User.objects.filter(query)


@login_required
def view_scheduler_slots(request):
    data = []
    filtered_users = _filter_users_on_query(request)
    phase_focus = None

    if request.GET.get('job'):
        job = get_object_or_404(Job, pk=int(request.GET.get('job')))
        if request.GET.get('phase'):
            phase_focus = get_object_or_404(Phase, job=job, pk=int(request.GET.get('phase')))
        else:
            phase_focus = job
    for user in filtered_users:
        data = data + user.get_timeslots(
            start=request.GET.get('start', None),
            end=request.GET.get('end', None), phase_focus=phase_focus)
        data = data + user.get_holidays(
            start=request.GET.get('start', None),
            end=request.GET.get('end', None),)
    return JsonResponse(data, safe=False)


@login_required
def view_scheduler_members(request):
    data = []
    filtered_users = _filter_users_on_query(request)
    for user in filtered_users:
        user_title = str(user)
        main_org = user.unit_memberships.first()
        data.append({
            "id": user.pk,
            "title": user_title,
            "businessHours": {
                "startTime": main_org.unit.businessHours_startTime,
                "endTime": main_org.unit.businessHours_endTime,
                "daysOfWeek": main_org.unit.businessHours_days,
            } if main_org else {
                "startTime": "",
                "endTime": "",
                "daysOfWeek": "",
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
        if slot.is_delivery():
            form = DeliveryTimeSlotModalForm(request.POST, instance=slot)
        else:    
            form = NonDeliveryTimeSlotModalForm(request.POST, instance=slot)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
            data['form_errors'] = form.errors
    else:
        # Send the modal
        if slot.is_delivery():
            form = DeliveryTimeSlotModalForm(instance=slot)
        else:    
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

    job_id = request.GET.get('job', None)
    if job_id:
        job = get_object_or_404(Job, pk=job_id)
        phase_id = request.GET.get('phase', None)
        if phase_id:
            phase = get_object_or_404(Phase, pk=phase_id)
        else:
            phase = None
    else:
        job = None
        phase = None

    if request.method == 'POST':
        form = DeliveryTimeSlotModalForm(request.POST, start=start, end=end, user=user, phase=phase, job=job)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = DeliveryTimeSlotModalForm(start=start, end=end, user=user, phase=phase, job=job)

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