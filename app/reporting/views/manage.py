from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.shortcuts import get_object_or_404
from django.views.generic import UpdateView, DeleteView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _

from ..models import Report, ReportSchedule
from ..forms import ReportScheduleForm


class ReportUpdateView(LoginRequiredMixin, UpdateView):
    """View for editing report definition"""
    model = Report
    template_name = 'reporting/report_edit.html'
    context_object_name = 'report'
    fields = ['name', 'description', 'category', 'is_private']
    
    def get_success_url(self):
        messages.success(self.request, _('Report updated successfully.'))
        return reverse('reporting:report_detail', kwargs={'pk': self.object.pk})
    
    def get_queryset(self):
        # Ensure users can only edit their own reports
        return Report.objects.filter(created_by=self.request.user)


class ReportDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting a report"""
    model = Report
    template_name = 'reporting/report_confirm_delete.html'
    context_object_name = 'report'
    success_url = reverse_lazy('reporting:report_list')
    
    def get_queryset(self):
        # Ensure users can only delete their own reports
        return Report.objects.filter(created_by=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Report deleted successfully.'))
        return super().delete(request, *args, **kwargs)


class ReportScheduleCreateView(LoginRequiredMixin, CreateView):
    """View for creating a report schedule"""
    model = ReportSchedule
    form_class = ReportScheduleForm
    template_name = 'reporting/schedule_form.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass the report to the form
        kwargs['report'] = self.get_report()
        return kwargs
    
    def get_report(self):
        """Get the report for this schedule"""
        report_id = self.kwargs.get('report_id')
        return get_object_or_404(Report, pk=report_id, created_by=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = self.get_report()
        return context
    
    def form_valid(self, form):
        """Process the valid form"""
        # Set the report and created_by fields
        form.instance.report = self.get_report()
        form.instance.created_by = self.request.user
        
        messages.success(self.request, _('Schedule created successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('reporting:report_detail', kwargs={'pk': self.get_report().pk})


class ReportScheduleUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating a report schedule"""
    model = ReportSchedule
    form_class = ReportScheduleForm
    template_name = 'reporting/schedule_form.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass the report to the form
        kwargs['report'] = self.object.report
        return kwargs
    
    def get_queryset(self):
        # Ensure users can only edit their own schedules
        return ReportSchedule.objects.filter(report__created_by=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = self.object.report
        return context
    
    def form_valid(self, form):
        messages.success(self.request, _('Schedule updated successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('reporting:report_detail', kwargs={'pk': self.object.report.pk})


class ReportScheduleDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting a report schedule"""
    model = ReportSchedule
    template_name = 'reporting/schedule_confirm_delete.html'
    context_object_name = 'schedule'
    
    def get_queryset(self):
        # Ensure users can only delete their own schedules
        return ReportSchedule.objects.filter(report__created_by=self.request.user)
    
    def get_success_url(self):
        return reverse('reporting:report_detail', kwargs={'pk': self.object.report.pk})
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Schedule deleted successfully.'))
        return super().delete(request, *args, **kwargs)