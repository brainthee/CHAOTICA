from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponseRedirect, Http404
from django.views.generic import ListView, DetailView, DeleteView
from django.views.decorators.http import require_POST
from django.db.models import Q
import logging

from ..models import Report, ReportCategory, ReportFilter
from ..services.data_service import DataService
from ..services.export_service import ExportService
from ..permissions import (
    can_view_report, can_edit_report, can_delete_report, 
    ReportAccessMixin, ReportEditMixin, ReportDeleteMixin
)

import json
import datetime

@login_required
def index(request):
    """
    Report builder home page
    """
    # Get recent reports for this user
    user_reports = Report.objects.filter(owner=request.user).order_by('-updated_at')[:5]
    
    # Get public reports
    public_reports = Report.objects.filter(is_private=False).order_by('-updated_at')[:5]
    
    # Get favorite reports
    favorite_reports = request.user.favorite_reports.all().order_by('-updated_at')[:5]
    
    # Get report categories
    categories = ReportCategory.objects.all()
    
    return render(request, 'reporting/index.html', {
        'user_reports': user_reports,
        'public_reports': public_reports,
        'favorite_reports': favorite_reports,
        'categories': categories,
    })


class ReportListView(LoginRequiredMixin, ListView):
    """
    List all reports visible to the user
    """
    model = Report
    template_name = 'reporting/report_list.html'
    context_object_name = 'reports'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Filter by search term if provided
        search_term = self.request.GET.get('search', '')
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) | 
                Q(description__icontains=search_term)
            )
        
        # Filter by category if provided
        category = self.request.GET.get('category', '')
        if category and category.isdigit():
            queryset = queryset.filter(category_id=category)
        
        # Filter by visibility (my reports, public reports, etc.)
        view_type = self.request.GET.get('view', 'all')
        if view_type == 'my':
            queryset = queryset.filter(owner=user)
        elif view_type == 'public':
            queryset = queryset.filter(is_private=False)
        elif view_type == 'favorites':
            queryset = user.favorite_reports.all()
        else:
            # For 'all' view, show reports visible to this user
            if not user.is_superuser:
                queryset = queryset.filter(
                    Q(owner=user) | 
                    Q(is_private=False)
                )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_term'] = self.request.GET.get('search', '')
        context['view_type'] = self.request.GET.get('view', 'all')
        context['categories'] = ReportCategory.objects.all()
        context['selected_category'] = self.request.GET.get('category', '')
        return context


class ReportDetailView(ReportAccessMixin, DetailView):
    """
    View a report's details
    """
    model = Report
    template_name = 'reporting/report_detail.html'
    context_object_name = 'report'
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.object
        
        # Check if user can edit this report
        context['can_edit'] = can_edit_report(self.request.user, report)
        context['can_delete'] = can_delete_report(self.request.user, report)
        
        # Check if this is a favorite
        context['is_favorite'] = report.favorites.filter(id=self.request.user.id).exists()
        
        # Get the report fields
        context['fields'] = report.get_fields()
        
        # Get the filters
        context['filters'] = report.get_filters()
        
        # Get filter prompts that will be shown at runtime
        runtime_filters = report.filters.filter(prompt_at_runtime=True)
        context['runtime_filters'] = runtime_filters
        
        return context


@login_required
def run_report(request, uuid):
    """
    Run a report and show results
    """
    # Get the report
    report = get_object_or_404(Report, uuid=uuid)
    
    # Check if user can view this report
    if not can_view_report(request.user, report):
        messages.error(request, "You don't have permission to run this report.")
        return redirect('reporting:report_list')
    
    # Check if this is an export request
    export_format = request.GET.get('format')
    if export_format:
        return export_report(request, uuid, export_format)
    
    # Process any filter prompts
    filter_values = {}
    
    if request.method == 'POST':
        # Get filter values from form
        for key, value in request.POST.items():
            if key.startswith('filter_'):
                filter_id = key[7:]  # Remove 'filter_' prefix
                filter_values[filter_id] = value
        
        # Set export format if provided
        export_format = request.POST.get('export_format')
        if export_format:
            return export_report(request, uuid, export_format, filter_values)
    
    # Get any runtime filter prompts
    runtime_filters = report.filters.filter(prompt_at_runtime=True)
    
    if runtime_filters.exists() and not filter_values:
        # Show filter prompt form
        return render(request, 'reporting/report_filter_prompt.html', {
            'report': report,
            'runtime_filters': runtime_filters,
            'presentation_choices': Report.PRESENTATION_CHOICES if report.allow_presentation_choice else None,
        })
    
    # Run the report
    try:
        data = DataService.get_report_data(report, request.user, filter_values)
        
        # Set last_run_at datetime
        report.last_run_at = datetime.datetime.now()
        report.save(update_fields=['last_run_at'])
        
        # Get the fields for display
        fields = report.get_fields()
        
    except Exception as e:
        logger = logging.getLogger(__name__)

        import traceback
        logger.error(f"Error running report: {str(e)}")
        logger.error(traceback.format_exc())
        messages.error(request, f"Error running report: {str(e)}")
        return redirect('reporting:report_detail', uuid=report.uuid)
    
        # messages.error(request, f"Error running report: {str(e)}")
        # return redirect('reporting:report_detail', uuid=report.uuid)
    
    # Show results
    return render(request, 'reporting/report_results.html', {
        'report': report,
        'fields': fields,
        'data': data,
        'filter_values': filter_values,
        'runtime_filters': runtime_filters,
        'presentation_choices': Report.PRESENTATION_CHOICES if report.allow_presentation_choice else None,
    })


def export_report(request, uuid, format_type, filter_values=None):
    """
    Export a report in the specified format
    """
    # Get the report
    report = get_object_or_404(Report, uuid=uuid)
    
    # Check if user can view this report
    if not can_view_report(request.user, report):
        messages.error(request, "You don't have permission to run this report.")
        return redirect('reporting:report_list')
    
    # Set default filter values
    if filter_values is None:
        filter_values = {}
        
        # Get filter values from GET params
        for key, value in request.GET.items():
            if key.startswith('filter_'):
                filter_id = key[7:]  # Remove 'filter_' prefix
                filter_values[filter_id] = value
    
    # Run the report
    try:
        data = DataService.get_report_data(report, request.user, filter_values)
        
        # Set last_run_at datetime
        report.last_run_at = datetime.datetime.now()
        report.save(update_fields=['last_run_at'])
        
        # Get the fields for display
        fields = report.get_fields()
        
    except Exception as e:
        messages.error(request, f"Error running report: {str(e)}")
        return redirect('reporting:report_detail', uuid=report.uuid)
    
    # Export the data
    try:
        return ExportService.export_report(report, data, format_type)
    except Exception as e:
        messages.error(request, f"Error exporting report: {str(e)}")
        return redirect('reporting:report_detail', uuid=report.uuid)


class ReportDeleteView(ReportDeleteMixin, DeleteView):
    """
    Delete a report
    """
    model = Report
    template_name = 'reporting/report_confirm_delete.html'
    context_object_name = 'report'
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'
    
    def get_success_url(self):
        messages.success(self.request, "Report deleted successfully.")
        return reverse('reporting:report_list')


@login_required
@require_POST
def toggle_favorite(request, uuid):
    """
    Toggle favorite status of a report
    """
    report = get_object_or_404(Report, uuid=uuid)
    
    # Check if user can view this report
    if not can_view_report(request.user, report):
        return JsonResponse({'status': 'error', 'message': "You don't have permission to access this report."})
    
    # Toggle favorite status
    if report.favorites.filter(id=request.user.id).exists():
        report.favorites.remove(request.user)
        is_favorite = False
    else:
        report.favorites.add(request.user)
        is_favorite = True
    
    return JsonResponse({'status': 'success', 'is_favorite': is_favorite})


@login_required
def create_category(request):
    """
    Create a new report category
    """
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        
        if not name:
            messages.error(request, "Category name cannot be empty.")
            return redirect('reporting:report_list')
        
        # Check if category already exists
        if ReportCategory.objects.filter(name=name).exists():
            messages.error(request, "Category with this name already exists.")
            return redirect('reporting:report_list')
        
        # Create the category
        category = ReportCategory.objects.create(
            name=name,
            description=description
        )
        
        messages.success(request, f"Category '{name}' created successfully.")
        return redirect('reporting:report_list')
    
    # Show form
    return render(request, 'reporting/category_form.html', {
        'categories': ReportCategory.objects.all(),
    })