from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.http import HttpResponseRedirect, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden
from django.template import loader
from django.db.models import Q
from django.conf import settings
from guardian.core import ObjectPermissionChecker
from guardian.shortcuts import get_objects_for_user
from guardian.mixins import PermissionRequiredMixin
from django.views import View
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from chaotica_utils.enums import UnitRoles
from ..models import Job, TimeSlot, TimeSlotType, OrganisationalUnit, WorkflowTask, Contact
from ..forms import ScopeInlineForm, DeliveryChangeTimeSlotModalForm, AddNote, JobForm, AssignUserField, ScopeForm
from ..enums import JobStatuses, TimeSlotDeliveryRole, DefaultTimeSlotTypes
from .helpers import _process_assign_user, _process_assign_contact
import logging
from django.contrib.auth.decorators import login_required, permission_required


logger = logging.getLogger(__name__)

# TODO: setup events for schedule so it comes back with member's only 

@login_required
@permission_required('jobtracker.view_schedule', (Job, 'slug', 'slug'))
def view_job_schedule_slots(request, slug):
    data = []
    job = get_object_or_404(Job, slug=slug)
    slots = TimeSlot.objects.filter(phase__job=job)
    for slot in slots:
        data.append(
            slot.get_schedule_json(
                url=reverse('change_job_schedule_slot', kwargs={"slug":job.slug, "pk":slot.pk})
            )
        )
    return JsonResponse(data, safe=False)


@login_required
@permission_required('jobtracker.view_schedule', (Job, 'slug', 'slug'))
def view_job_schedule_members(request, slug):
    data = []
    job = get_object_or_404(Job, slug=slug)
    scheduled_users = job.team_scheduled()
    if scheduled_users:
        for user in scheduled_users:
            data.append({
                "id": user.pk,
                "title": str(user),
                "businessHours": {
                    "startTime": job.unit.businessHours_startTime,
                    "endTime": job.unit.businessHours_endTime,
                    "daysOfWeek": job.unit.businessHours_days,
                }
            })
    return JsonResponse(data, safe=False)


@login_required
@permission_required('jobtracker.assign_poc', (Job, 'slug', 'slug'))
def assign_job_poc(request, slug):
    job = get_object_or_404(Job, slug=slug)
    contacts = Contact.objects.filter(company=job.client)
    return _process_assign_contact(request, job, 'primary_client_poc', contacts=contacts)


@login_required
@permission_required('jobtracker.change_job', (Job, 'slug', 'slug'))
def assign_job_field(request, slug, field):
    valid_fields = [
        'account_manager', 'dep_account_manager',
        'scoped_by', 'scoped_signed_off_by'
    ]
    job = get_object_or_404(Job, slug=slug)
    if field in valid_fields:
        if field == "scoped_by":
            return _process_assign_user(request, job, field, multiple=True)
        else:
            return _process_assign_user(request, job, field)
    else:
        return HttpResponseBadRequest()


@login_required
@permission_required('jobtracker.change_job', (Job, 'slug', 'slug'))
def assign_job_scoped(request, slug):
    job = get_object_or_404(Job, slug=slug)
    return _process_assign_user(request, job, 'scoped_by', multiple=True)


@login_required
@permission_required('jobtracker.scope_job', (Job, 'slug', 'slug'))
def job_edit_scope(request, slug):
    is_ajax = False
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        is_ajax = True
    
    job = get_object_or_404(Job, slug=slug)
    data = {}
    data['form_is_valid'] = False
    if request.method == 'POST':
        form = ScopeInlineForm(request.POST, instance=job)
        if form.is_valid():
            job = form.save()
            # add activity logs
            data['form_is_valid'] = True
            data['changed_data'] = form.changed_data
            log_system_activity(job, "Scope edited ("+', '.join(form.changed_data)+")")
            if not is_ajax:
                return HttpResponseRedirect(reverse('job_detail', kwargs={'slug': slug}))
    else:
        form = ScopeInlineForm(instance=job)  
    
    context = {'scopeInlineForm': form, 'job': job}
    data['html_form'] = loader.render_to_string("partials/job/forms/scope.html",
                                                context,
                                                request=request)

    return JsonResponse(data)


@permission_required('jobtracker.change_schedule', (Job, 'slug', 'slug'))
def change_job_schedule_slot(request, slug, pk=None):
    job = get_object_or_404(Job, slug=slug)
    slot = None
    if pk:
        slot = get_object_or_404(TimeSlot, pk=pk, phase__job=job)
    data = dict()
    if request.method == "POST":
        form = DeliveryChangeTimeSlotModalForm(request.POST, instance=slot, slug=slug)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.slot_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
            slot.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
            data['form_errors'] = form.errors
    else:
        # Send the modal
        form = DeliveryChangeTimeSlotModalForm(instance=slot, slug=slug)

    context = {'form': form, 'job': job}
    data['html_form'] = loader.render_to_string("jobtracker/modals/job_slot.html",
                                                context,
                                                request=request)
    return JsonResponse(data)


@login_required
@permission_required('jobtracker.add_note', (Job, 'slug', 'slug'))
def job_create_note(request, slug):
    job = get_object_or_404(Job, slug=slug)
    if request.method == 'POST':
        form = AddNote(request.POST)
        if form.is_valid():
            new_note = form.save(commit=False)
            new_note.content_object = job
            new_note.author = request.user
            new_note.is_system_note = False
            new_note.save()
            return HttpResponseRedirect(reverse('job_detail', kwargs={"slug": slug})+"#notes")
    return HttpResponseBadRequest()


class JobBaseView(ChaoticaBaseView, View):
    model = Job
    fields = '__all__'

    def get_success_url(self):
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
            return reverse_lazy('job_detail', kwargs={'slug': slug})
        else:
            return reverse_lazy('job_list')

    def get_context_data(self, **kwargs):
        context = super(JobBaseView, self).get_context_data(**kwargs)
        note_form = AddNote()
        context['note_form'] = note_form
        return context


class JobListView(JobBaseView, ListView):
    def get_queryset(self):
        # Only return jobs with:
        # - permission
        # - isn't deleted
        # - isn't archived
        # get our units 
        units = OrganisationalUnit.objects.filter(
            pk__in=self.request.user.unit_memberships.filter(role__in=UnitRoles.get_roles_with_permission('jobtracker.view_job')).values_list('unit').distinct())
        my_jobs = get_objects_for_user(self.request.user, 'jobtracker.view_job')
        jobs = Job.objects.filter(Q(unit__in=units)|Q(pk__in=my_jobs)).exclude(status=JobStatuses.DELETED).exclude(status=JobStatuses.ARCHIVED)
        return jobs


# @permission_required('jobtracker.view_job', (Job, 'slug', 'slug'))
class JobDetailView(PermissionRequiredMixin, JobBaseView, DetailView):
    permission_required = 'jobtracker.view_job'

    def check_permissions(self, request):
        obj = self.get_permission_object()
        checker = ObjectPermissionChecker(self.request.user)
        if obj:
            if self.request.user.is_authenticated:
                units = OrganisationalUnit.objects.filter(
                    pk__in=self.request.user.unit_memberships.filter(
                        role__in=UnitRoles.get_roles_with_permission('jobtracker.view_job')).values_list('unit').distinct()
                        )
                
                if obj.unit in units or checker.has_perm('view_job', obj):
                    return None
            else:
                from django.contrib.auth.views import redirect_to_login
                login_url = settings.LOGIN_URL
                return redirect_to_login(request.get_full_path(),
                                        login_url,
                                        'next')
        return HttpResponseForbidden()

    def get_context_data(self, **kwargs):
        context = super(JobDetailView, self).get_context_data(**kwargs)
        
        scope_inline_form = ScopeInlineForm(instance=context['job'])
        context['scopeInlineForm'] = scope_inline_form

        return context


class JobCreateView(JobBaseView, CreateView):
    template_name = "jobtracker/job_form_create.html"
    form_class = JobForm
    fields = None

    # Permissions are handled in the unit selection box... weirdly!

    def get_success_url(self):
        return reverse_lazy('job_detail', kwargs={'slug': self.object.slug})

    def get_form_kwargs(self):
        kwargs = super(JobCreateView, self).get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.save()
        log_system_activity(form.instance, "Created Job", author=form.instance.created_by)
        return super().form_valid(form)
    

class JobUpdateView(PermissionRequiredMixin, JobBaseView, UpdateView):
    permission_required = 'jobtracker.change_job'
    return_403 = True
    template_name = "jobtracker/job_form_edit.html"
    form_class = JobForm
    fields = None
    """View to update a job"""

    def get_form_kwargs(self):
        kwargs = super(JobUpdateView, self).get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs

    def form_valid(self, form):
        log_system_activity(form.instance, "Job Updated")
        return super().form_valid(form)


class JobUpdateScopeView(PermissionRequiredMixin, JobBaseView, UpdateView):
    permission_required = 'jobtracker.scope_job'
    return_403 = True
    model = Job
    template_name = "jobtracker/job_form_scope.html"
    form_class = ScopeForm
    fields = None

    def get_form_kwargs(self):
        kwargs = super(JobUpdateView, self).get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs

    def form_valid(self, form):
        log_system_activity(form.instance, "Scope Updated")
        return super().form_valid(form)    


class JobScheduleView(PermissionRequiredMixin, JobBaseView, DetailView):
    permission_required = 'jobtracker.view_schedule'
    return_403 = True
    """ Renders the schedule for the job """
    template_name = "jobtracker/job_schedule.html"

    def get_context_data(self, **kwargs):
        context = super(JobScheduleView, self).get_context_data(**kwargs)
        context['userSelect'] = AssignUserField()
        context['TimeSlotDeliveryRoles'] = TimeSlotDeliveryRole.CHOICES

        types_in_use = context['job'].get_all_total_scheduled_by_type()
        context['TimeSlotDeliveryRolesInUse'] = types_in_use
        return context
    

class JobDeleteView(PermissionRequiredMixin, JobBaseView, DeleteView):
    permission_required = 'jobtracker.delete_job'
    return_403 = True
    """View to delete a job"""
        

@login_required
def job_update_workflow(request, slug, new_state):
    job = get_object_or_404(Job, slug=slug)
    data = dict()
    new_state_str = None
    try:
        for state in JobStatuses.CHOICES:
            if state[0] == new_state:
                new_state_str = state[1]
        if new_state_str == None:
            raise TypeError()
    except Exception:
        return HttpResponseBadRequest()
    
    can_proceed = True
        
    if new_state == JobStatuses.PENDING_SCOPE:
        if job.can_to_pending_scope(request):
            if request.method == 'POST':
                job.to_pending_scope(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.SCOPING:
        if job.can_to_scoping(request):
            if request.method == 'POST':
                if not job.scoped_by.all():
                    if request.user.has_perm('scope_job'):
                        # No one is defined to scope and we have permission - auto add!
                        job.scoped_by.add(request.user)
                        job.save()
                job.to_scoping(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED:
        if job.can_to_additional_scope_req(request):
            if request.method == 'POST':
                job.to_additional_scope_req(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.PENDING_SCOPING_SIGNOFF:
        if job.can_to_scope_pending_signoff(request):
            if request.method == 'POST':
                job.to_scope_pending_signoff(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.SCOPING_COMPLETE:
        if job.can_to_scope_complete(request):
            if request.method == 'POST':
                job.to_scope_complete(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.PENDING_START:
        if job.can_to_pending_start(request):
            if request.method == 'POST':
                job.to_pending_start(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.IN_PROGRESS:
        if job.can_to_in_progress(request):
            if request.method == 'POST':
                job.to_in_progress(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.COMPLETED:
        if job.can_to_complete(request):
            if request.method == 'POST':
                job.to_complete(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.LOST:
        if job.can_to_lost(request):
            if request.method == 'POST':
                job.to_lost(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.DELETED:
        if job.can_to_delete(request):
            if request.method == 'POST':
                job.to_delete(request.user)
        else:
            can_proceed = False
    elif new_state == JobStatuses.ARCHIVED:
        if job.can_to_archive(request):
            if request.method == 'POST':
                job.to_archive(request.user)
        else:
            can_proceed = False
    else:
        return HttpResponseBadRequest()

        # sendWebHookStatusAlert(redteam=rt, title="Engagement Status Changed", msg="Engagement "+rt.projectName+" status has changed to: "+str(dict(RTState.choices).get(new_state)))
        
    if request.method == 'POST' and can_proceed:
        job.save()
        data['form_is_valid'] = True  # This is just to play along with the existing code
    
    tasks = WorkflowTask.objects.filter(appliedModel=WorkflowTask.WF_JOB, status=new_state)
    context = {
        'job': job,
        'can_proceed': can_proceed,
        'new_state_str': new_state_str,
        'new_state': new_state,
        'tasks': tasks,
        }
    data['html_form'] = loader.render_to_string('jobtracker/modals/job_workflow.html',
                                                context,
                                                request=request)
    return JsonResponse(data)
