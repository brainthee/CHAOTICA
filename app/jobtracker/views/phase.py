from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponseRedirect, HttpResponseBadRequest, JsonResponse
from django.template import loader
from django.views import View
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView, pageDefaults
from chaotica_utils.utils import *
from ..models import *
from ..forms import *
from ..tasks import *
from ..enums import FeedbackType, PhaseStatuses, TimeSlotDeliveryRole
from .helpers import _process_assign_user
import logging
from django.contrib.auth.decorators import login_required


logger = logging.getLogger(__name__)


@login_required
def view_phase_schedule_slots(request, jobSlug, slug):
    data = []
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    slots = TimeSlot.objects.filter(phase=phase)
    for slot in slots:
        data.append(slot.get_schedule_phase_json())
    return JsonResponse(data, safe=False)


@login_required
def view_phase_schedule_members(request, jobSlug, slug):
    data = []
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    scheduledUsers = phase.team()
    if scheduledUsers:
        for user in scheduledUsers:
            userTitle = str(user)
            role = ""
            if phase.project_lead == user:
                if role:
                    role += ',Lead'
                else:
                    role += 'Lead'
            if phase.report_author == user:
                if role:
                    role += ', Author'
                else:
                    role += 'Author'
            if phase.techqa_by == user:
                if role:
                    role += ', TQA'
                else:
                    role += 'TQA'
            if phase.presqa_by == user:
                if role:
                    role += ', PQA'
                else:
                    role += 'PQA'
            if role:
                userTitle = userTitle+" ("+role+")"
            data.append({
                "id": user.pk,
                "title": userTitle,
                "role": role,
                "businessHours": {
                    "startTime": job.unit.businessHours_startTime,
                    "endTime": job.unit.businessHours_endTime,
                    "daysOfWeek": job.unit.businessHours_days,
                }
            })
    return JsonResponse(data, safe=False)


@login_required
def assign_phase_field(request, jobSlug, slug, field):
    validFields = [
        'project_lead', 'report_author',
        'techqa_by', 'presqa_by'
    ]
    phase = get_object_or_404(Phase, slug=slug, job__slug=jobSlug)
    if field in validFields:
        return _process_assign_user(request, phase, field)
    else:
        return HttpResponseBadRequest()
    

class PhaseBaseView(ChaoticaBaseView, View):
    model = Phase
    fields = '__all__'
    jobSlug = None

    def get_success_url(self):
        if 'slug' in self.kwargs:
            slug = self.kwargs['slug']
            if 'jobSlug' in self.kwargs:
                jobSlug = self.kwargs['jobSlug']
                return reverse_lazy('phase_detail', kwargs={'jobSlug': jobSlug, 'slug': slug})
        else:
            if 'jobSlug' in self.kwargs:
                jobSlug = self.kwargs['jobSlug']
                return reverse_lazy('job_detail', kwargs={'slug': jobSlug})

    def get_context_data(self, **kwargs):
        context = super(PhaseBaseView, self).get_context_data(**kwargs)
        if 'jobSlug' in self.kwargs:
            context['job'] = get_object_or_404(Job, slug=self.kwargs['jobSlug'])

        noteForm = AddNote()
        context['noteForm'] = noteForm

        return context

class PhaseDetailView(PhaseBaseView, DetailView):

    def get_context_data(self, **kwargs):
        context = super(PhaseDetailView, self).get_context_data(**kwargs)
        
        deliverForm = PhaseDeliverInlineForm(instance=context['phase'])
        context['phaseDeliverInlineForm'] = deliverForm
        
        infoForm = PhaseForm(instance=context['phase'])
        context['infoForm'] = infoForm
        
        
        if context['phase'].status == PhaseStatuses.QA_TECH:
            qaForm = PhaseTechQAInlineForm(instance=context['phase'])
            context['feedbackForm'] = qaForm
        
        if context['phase'].status == PhaseStatuses.QA_PRES:
            qaForm = PhasePresQAInlineForm(instance=context['phase'])
            context['feedbackForm'] = qaForm

        return context

class PhaseCreateView(PhaseBaseView, CreateView):
    form_class = PhaseForm
    template_name = "jobtracker/phase_form_create.html"
    fields = None

    def form_valid(self, form):
        form.instance.job = Job.objects.get(slug=self.kwargs['jobSlug'])    
        form.instance.save()
        log_system_activity(form.instance, "Created")    
        return super(PhaseCreateView, self).form_valid(form)

    def get_form_kwargs(self):
        kwargs = super(PhaseCreateView, self).get_form_kwargs()
        if 'jobSlug' in self.kwargs:
            kwargs['job'] = get_object_or_404(Job, slug=self.kwargs['jobSlug'])
        return kwargs

@login_required
def PhaseCreateNote(request, jobSlug, slug):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    if request.method == 'POST':
        form = AddNote(request.POST)
        if form.is_valid():
            newNote = form.save(commit=False)
            newNote.content_object = phase
            newNote.author = request.user
            newNote.is_system_note = False
            newNote.save()      
            return HttpResponseRedirect(reverse('phase_detail', kwargs={"jobSlug": jobSlug,"slug": slug})+"#notes")
    return HttpResponseBadRequest()

class PhaseScheduleView(PhaseBaseView, DetailView):
    """ Renders the schedule for the job """
    template_name = "jobtracker/phase_schedule.html"

    def get_context_data(self, **kwargs):
        context = super(PhaseScheduleView, self).get_context_data(**kwargs)
        context['userSelect'] = AssignUserField()
        context['TimeSlotDeliveryRoles'] = TimeSlotDeliveryRole.CHOICES

        typesInUse = context['phase'].get_all_total_scheduled_by_type()
        context['TimeSlotDeliveryRolesInUse'] = typesInUse
        return context

class PhaseUpdateView(PhaseBaseView, UpdateView):
    form_class = PhaseForm
    template_name = "jobtracker/phase_form.html"
    fields = None

    # This is useful for formsets. Don't need it here any more but keep it just in case. 
    # def get_context_data(self, **kwargs):
    #     context = super(PhaseUpdateView, self).get_context_data(**kwargs)
    #     context['timeAllocations'] = TimeAllocationFormSet(queryset=TimeAllocation.objects.filter(phase=context['phase']))
    #     context['taHelper'] = TimeAllocationForm()
    #     # context['form'] = PhaseForm()
    #     return context

    # def post(self, request, *args, **kwargs):
    #     phase = get_object_or_404(Phase, slug=kwargs['slug'])
    #     timeAllocations = TimeAllocationFormSet(request.POST)
    #     form = PhaseForm(request.POST, instance=phase)
    #     if timeAllocations.is_valid() and form.is_valid():
    #         return self.form_valid(timeAllocations,form)

    # def form_valid(self, timeAllocations,form):
    #     phase = form.save()
    #     instances = timeAllocations.save(commit=False)
    #     for instance in instances:
    #         instance.phase = phase
    #         instance.save()
    #     return HttpResponseRedirect(phase.get_absolute_url())

    def get_form_kwargs(self):
        kwargs = super(PhaseUpdateView, self).get_form_kwargs()
        if 'jobSlug' in self.kwargs:
            kwargs['job'] = get_object_or_404(Job, slug=self.kwargs['jobSlug'])
        return kwargs



@login_required
def phase_edit_delivery(request, jobSlug, slug):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    if request.method == 'POST':
        form = PhaseDeliverInlineForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
            return redirect('phase_detail', jobSlug, slug)    
        else:
            data['form_is_valid'] = False
    else:
        form = PhaseDeliverInlineForm(instance=phase)

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/feedback_form.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

@login_required
def phase_feedback_techqa(request, jobSlug, slug):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    
    data = dict()
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.author = request.user
            feedback.phase = phase
            feedback.feedbackType = FeedbackType.TECH
            feedback.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = FeedbackForm()

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/feedback_form.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

@login_required
def phase_feedback_presqa(request, jobSlug, slug):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    
    data = dict()
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.author = request.user
            feedback.phase = phase
            feedback.feedbackType = FeedbackType.PRES
            feedback.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = FeedbackForm()

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/feedback_form.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

@login_required
def phase_feedback_scope(request, jobSlug, slug):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    
    data = dict()
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.author = request.user
            feedback.phase = phase
            feedback.feedbackType = FeedbackType.SCOPE
            feedback.save()
            data['form_is_valid'] = True
        else:
            data['form_is_valid'] = False
    else:
        form = FeedbackForm()

    context = {'form': form}
    data['html_form'] = loader.render_to_string("jobtracker/modals/feedback_form.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

@login_required
def phase_rating_techqa(request, jobSlug, slug):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    
    data = dict()
    if request.method == 'POST':
        form = PhaseTechQAInlineForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
            data['changed_data'] = form.changed_data
        else:
            data['form_is_valid'] = False
    else:
        form = PhaseTechQAInlineForm(instance=phase)

    context = {'feedbackForm': form}
    data['html_form'] = loader.render_to_string("partials/phase/widgets/feedback.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

@login_required
def phase_rating_presqa(request, jobSlug, slug):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    
    data = dict()
    if request.method == 'POST':
        form = PhasePresQAInlineForm(request.POST, instance=phase)
        if form.is_valid():
            form.save()
            data['form_is_valid'] = True
            data['changed_data'] = form.changed_data
        else:
            data['form_is_valid'] = False
    else:
        form = PhasePresQAInlineForm(instance=phase)

    context = {'feedbackForm': form}
    data['html_form'] = loader.render_to_string("partials/phase/widgets/feedback.html",
                                                context,
                                                request=request)
    return JsonResponse(data)

@login_required
def PhaseUpdateWorkflow(request, jobSlug, slug, newState):
    job = get_object_or_404(Job, slug=jobSlug)
    phase = get_object_or_404(Phase, job=job, slug=slug)
    data = dict()
    newStateStr = None
    try:
        for state in PhaseStatuses.CHOICES:
            if state[0] == newState:
                newStateStr = state[1]
        if newStateStr == None:
            raise TypeError()
    except Exception:
        return HttpResponseBadRequest()
    
    canProceed = True
        
    if newState == PhaseStatuses.PENDING_SCHED:
        if phase.can_to_pending_sched(request):
            if request.method == 'POST':
                phase.to_pending_sched()
        else:
            canProceed = False
    elif newState == PhaseStatuses.SCHEDULED_TENTATIVE:
        if phase.can_to_sched_tentative(request):
            if request.method == 'POST':
                phase.to_sched_tentative()
        else:
            canProceed = False
    elif newState == PhaseStatuses.SCHEDULED_CONFIRMED:
        if phase.can_to_sched_confirmed(request):
            if request.method == 'POST':
                phase.to_sched_confirmed()
        else:
            canProceed = False
    elif newState == PhaseStatuses.PRE_CHECKS:
        if phase.can_to_pre_checks(request):
            if request.method == 'POST':
                phase.to_pre_checks()
        else:
            canProceed = False
    elif newState == PhaseStatuses.CLIENT_NOT_READY:
        if phase.can_to_not_ready(request):
            if request.method == 'POST':
                phase.to_not_ready()
        else:
            canProceed = False
    elif newState == PhaseStatuses.READY_TO_BEGIN:
        if phase.can_to_ready(request):
            if request.method == 'POST':
                phase.to_ready()
        else:
            canProceed = False
    elif newState == PhaseStatuses.IN_PROGRESS:
        if phase.can_to_in_progress(request):
            if request.method == 'POST':
                phase.to_in_progress()
        else:
            canProceed = False
    elif newState == PhaseStatuses.QA_TECH:
        if phase.can_to_tech_qa(request):
            if request.method == 'POST':
                phase.to_tech_qa()
        else:
            canProceed = False
    elif newState == PhaseStatuses.QA_TECH_AUTHOR_UPDATES:
        if phase.can_to_tech_qa_updates(request):
            if request.method == 'POST':
                phase.to_tech_qa_updates()
        else:
            canProceed = False
    elif newState == PhaseStatuses.QA_PRES:
        if phase.can_to_pres_qa(request):
            if request.method == 'POST':
                phase.to_pres_qa()
        else:
            canProceed = False
    elif newState == PhaseStatuses.QA_PRES_AUTHOR_UPDATES:
        if phase.can_to_pres_qa_updates(request):
            if request.method == 'POST':
                phase.to_pres_qa_updates()
        else:
            canProceed = False
    elif newState == PhaseStatuses.COMPLETED:
        if phase.can_to_completed(request):
            if request.method == 'POST':
                phase.to_completed()
        else:
            canProceed = False
    elif newState == PhaseStatuses.DELIVERED:
        if phase.can_to_delivered(request):
            if request.method == 'POST':
                phase.to_delivered()
        else:
            canProceed = False
    elif newState == PhaseStatuses.CANCELLED:
        if phase.can_to_cancelled(request):
            if request.method == 'POST':
                phase.to_cancelled()
        else:
            canProceed = False
    elif newState == PhaseStatuses.POSTPONED:
        if phase.can_to_postponed(request):
            if request.method == 'POST':
                phase.to_postponed()
        else:
            canProceed = False
    elif newState == PhaseStatuses.DELETED:
        if phase.can_to_deleted(request):
            if request.method == 'POST':
                phase.to_deleted()
        else:
            canProceed = False
    elif newState == PhaseStatuses.ARCHIVED:
        if phase.can_to_archived(request):
            if request.method == 'POST':
                phase.to_archived()
        else:
            canProceed = False
    else:
        return HttpResponseBadRequest()

        # sendWebHookStatusAlert(redteam=rt, title="Engagement Status Changed", msg="Engagement "+rt.projectName+" status has changed to: "+str(dict(RTState.choices).get(newState)))
        
    if request.method == 'POST' and canProceed:
        phase.save()
        log_system_activity(phase, "Moved to "+newStateStr)
        data['form_is_valid'] = True  # This is just to play along with the existing code
    
    tasks = WorkflowTasks.objects.filter(appliedModel=WorkflowTasks.WF_PHASE, status=newState)
    context = {
        'job': job,
        'phase': phase,
        'canProceed': canProceed,
        'newStateStr': newStateStr,
        'newState': newState,
        'tasks': tasks,
        }
    data['html_form'] = loader.render_to_string('jobtracker/modals/phase_workflow.html',
                                                context,
                                                request=request)
    return JsonResponse(data)

class PhaseDeleteView(PhaseBaseView, DeleteView):
    """View to delete a job"""    