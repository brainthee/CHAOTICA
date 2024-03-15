from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import Qualification, AwardingBody
from ..forms import QualificationForm, AwardingBodyForm
import logging


logger = logging.getLogger(__name__)


class QualificationAwardingBodyBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = AwardingBody
    fields = '__all__'
    permission_required = 'jobtracker.view_awardingbody'
    return_403 = True
    accept_global_perms = True
    success_url = reverse_lazy('qualification_list')


class QualificationAwardingBodyCreateView(QualificationAwardingBodyBaseView, PermissionRequiredMixin, CreateView):
    form_class = AwardingBodyForm
    fields = None
    permission_required = 'jobtracker.add_awardingbody'
    permission_object = AwardingBody
    return_403 = True
    accept_global_perms = True


class QualificationAwardingUpdateView(QualificationAwardingBodyBaseView, PermissionRequiredMixin, UpdateView):
    form_class = AwardingBodyForm
    fields = None
    permission_required = 'jobtracker.change_awardingbody'
    return_403 = True
    accept_global_perms = True


class QualificationAwardingDeleteView(QualificationAwardingBodyBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""
    permission_required = 'jobtracker.delete_awardingbody'
    return_403 = True
    accept_global_perms = True


class QualificationBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Qualification
    fields = '__all__'
    permission_required = 'jobtracker.view_qualification'
    accept_global_perms = True
    return_403 = True


    def get_context_data(self, **kwargs):
        context = super(QualificationBaseView, self).get_context_data(**kwargs)
        # Get categories
        context['awarding_bodies'] = AwardingBody.objects.all()
        return context
    
    def get_success_url(self):
        if 'slug' in self.kwargs and 'bodySlug' in self.kwargs:
            slug = self.kwargs['slug']
            bodySlug = self.kwargs['bodySlug']
            return reverse_lazy('qualification_detail', kwargs={'bodySlug': bodySlug, 'slug': slug})
        else:
            return reverse_lazy('qualification_list')


class QualificationListView(QualificationBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


class QualificationDetailView(QualificationBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = 'jobtracker.view_qualification'
    accept_global_perms = True
    return_403 = True


class QualificationCreateView(QualificationBaseView, PermissionRequiredMixin, CreateView):
    form_class = QualificationForm
    fields = None
    permission_required = 'jobtracker.add_qualification'
    accept_global_perms = True
    permission_object = Qualification
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(QualificationCreateView, self).get_context_data(**kwargs)
        # Get categories
        context['awardingbody'] = AwardingBody.objects.get(slug=self.kwargs['bodySlug'])     
        return context

    def form_valid(self, form):
        form.instance.awarding_body = AwardingBody.objects.get(slug=self.kwargs['bodySlug'])        
        return super(QualificationCreateView, self).form_valid(form)


class QualificationUpdateView(QualificationBaseView, PermissionRequiredMixin, UpdateView):
    form_class = QualificationForm
    fields = None

    permission_required = 'jobtracker.change_qualification'
    accept_global_perms = True
    return_403 = True


class QualificationDeleteView(QualificationBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = 'jobtracker.delete_qualification'
    accept_global_perms = True
    return_403 = True
    