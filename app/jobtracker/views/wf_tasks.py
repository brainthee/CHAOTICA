from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import WorkflowTask
from ..forms import WFTaskForm
from ..enums import PhaseStatuses, JobStatuses
import logging
from pprint import pprint


logger = logging.getLogger(__name__)

class WFTaskBaseView(ChaoticaBaseView):
    model = WorkflowTask
    fields = '__all__'

    def get_success_url(self):
        return reverse_lazy('wf_tasks_list')

class WFTaskListView(WFTaskBaseView, ListView):
    pass

class WFTaskDetailView(WFTaskBaseView, DetailView):
    pass

class WFTaskCreateView(WFTaskBaseView, CreateView):
    form_class = WFTaskForm
    fields = None

    def get_context_data(self, **kwargs):
        context = super(WFTaskCreateView, self).get_context_data(**kwargs)
        context['targetType'] = self.kwargs["targetType"]
        if self.kwargs["targetType"] == "job":
            context['applied_model'] = WorkflowTask.WF_JOB
            context['status_choices'] = JobStatuses.CHOICES
        elif self.kwargs["targetType"] == "phase":
            context['applied_model'] = WorkflowTask.WF_PHASE
            context['status_choices'] = PhaseStatuses.CHOICES     
        return context

    def get_form_kwargs(self):
        kwargs = super(WFTaskCreateView, self).get_form_kwargs()
        if self.kwargs["targetType"] == "job":
            kwargs['applied_model'] = WorkflowTask.WF_JOB
            kwargs['status_choices'] = JobStatuses.CHOICES
        elif self.kwargs["targetType"] == "phase":
            kwargs['applied_model'] = WorkflowTask.WF_PHASE
            kwargs['status_choices'] = PhaseStatuses.CHOICES    
        return kwargs

    def form_valid(self, form):
        if self.kwargs["targetType"] == "job":
            applied_model = WorkflowTask.WF_JOB
            status_choices = JobStatuses.CHOICES
        elif self.kwargs["targetType"] == "phase":
            applied_model = WorkflowTask.WF_PHASE
            status_choices = PhaseStatuses.CHOICES
        # Check if the status is valid...
        if form.instance.status > len(status_choices):
            # Invalid status
            form.add_error('status', 'Invalid status choice')
            return super(WFTaskCreateView, self).form_invalid(form)
        form.instance.appliedModel = applied_model
        return super(WFTaskCreateView, self).form_valid(form)

class WFTaskUpdateView(WFTaskBaseView, UpdateView):
    form_class = WFTaskForm
    fields = None

    def get_form_kwargs(self):
        kwargs = super(WFTaskUpdateView, self).get_form_kwargs()
        if kwargs["instance"].appliedModel == WorkflowTask.WF_JOB:
            kwargs['status_choices'] = JobStatuses.CHOICES
        elif kwargs["instance"].appliedModel == WorkflowTask.WF_PHASE:
            kwargs['status_choices'] = PhaseStatuses.CHOICES
        return kwargs

    def form_valid(self, form):
        if form.instance.appliedModel == WorkflowTask.WF_JOB:
            status_choices = JobStatuses.CHOICES
        elif form.instance.appliedModel == WorkflowTask.WF_PHASE:
            status_choices = PhaseStatuses.CHOICES

        # Check if the status is valid...
        if form.instance.status > len(status_choices):
            # Invalid status
            form.add_error('status', 'Invalid status choice')
            return super(WFTaskUpdateView, self).form_invalid(form)
        return super(WFTaskUpdateView, self).form_valid(form)

class WFTaskDeleteView(WFTaskBaseView, DeleteView):
    pass
    