import os

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from chaotica_utils.mixins import ObjectActivityMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponseRedirect, Http404, FileResponse
from django.views.generic import ListView, DetailView, DeleteView
from django.views.decorators.http import require_POST, require_safe, require_http_methods
from django.db.models import Q
import logging

from ..models import Report, ReportCategory, ReportFilter, ReportRun
from ..services.data_service import DataService
from ..services.export_service import ExportService
from ..permissions import (
    can_view_report, can_edit_report, can_delete_report,
    ReportAccessMixin, ReportEditMixin, ReportDeleteMixin
)

import json
from django.utils import timezone

@login_required
@require_safe
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


class ReportDetailView(ObjectActivityMixin, ReportAccessMixin, DetailView):
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


def _collect_filter_values(request):
    """Pull filter_<id> values out of POST (form) or GET (export links)."""
    filter_values = {}
    source = request.POST if request.method == 'POST' else request.GET
    for key, value in source.items():
        if key.startswith('filter_'):
            filter_values[key[7:]] = value  # strip 'filter_' prefix
    return filter_values


@login_required
@require_http_methods(["GET", "POST"])
def run_report(request, uuid):
    """
    Queue a report run in the background and show a progress page that polls
    until it's ready. Heavy reports no longer block the request (and so can't
    hit the ALB / nginx idle timeouts).
    """
    report = get_object_or_404(Report, uuid=uuid)

    if not can_view_report(request.user, report):
        messages.error(request, "You don't have permission to run this report.")
        return redirect('reporting:report_list')

    # None => on-screen HTML results. A value => a downloadable export.
    export_format = request.GET.get('format') or request.POST.get('export_format')

    filter_values = _collect_filter_values(request)

    # Prompt for runtime filters before queuing, if we don't have values yet.
    runtime_filters = report.filters.filter(prompt_at_runtime=True)
    if runtime_filters.exists() and not filter_values:
        return render(request, 'reporting/report_filter_prompt.html', {
            'report': report,
            'runtime_filters': runtime_filters,
            'presentation_choices': Report.PRESENTATION_CHOICES if report.allow_presentation_choice else None,
            # Preserve a requested download format across the prompt round-trip.
            'requested_format': export_format or '',
        })

    run = ReportRun.objects.create(
        report=report,
        user=request.user,
        filter_values=filter_values,
        export_format=export_format or None,
    )

    return render(request, 'reporting/report_running.html', {
        'report': report,
        'run': run,
        'status_url': reverse('reporting:report_run_status', args=[report.uuid, run.id]),
    })


def _get_run_or_404(request, uuid, run_id):
    report = get_object_or_404(Report, uuid=uuid)
    if not can_view_report(request.user, report):
        raise Http404()
    run = get_object_or_404(ReportRun, id=run_id, report=report)
    return report, run


@login_required
@require_safe
def report_run_status(request, uuid, run_id):
    """JSON status for a queued run; the progress page polls this."""
    report, run = _get_run_or_404(request, uuid, run_id)

    if run.status == ReportRun.STATUS_PENDING:
        position = ReportRun.objects.filter(
            status=ReportRun.STATUS_PENDING, created_at__lt=run.created_at
        ).count() + 1
        return JsonResponse({'status': 'pending', 'position': position,
                             'message': f'Queued (position {position})…'})

    if run.status == ReportRun.STATUS_RUNNING:
        duration = int((timezone.now() - run.started_at).total_seconds()) if run.started_at else 0
        return JsonResponse({'status': 'running', 'duration': duration,
                             'message': f'Running… ({duration}s)'})

    if run.status == ReportRun.STATUS_FAILED:
        return JsonResponse({'status': 'failed', 'message': run.error_message or 'Report run failed.'})

    # complete
    result_url = reverse('reporting:report_run_result', args=[report.uuid, run.id])
    return JsonResponse({
        'status': 'complete',
        'is_export': run.is_export,
        'row_count': run.row_count,
        'result_url': result_url,
    })


@login_required
@require_safe
def report_run_result(request, uuid, run_id):
    """Render the finished on-screen results, or stream the export download."""
    report, run = _get_run_or_404(request, uuid, run_id)

    if run.status != ReportRun.STATUS_COMPLETE:
        return redirect('reporting:report_detail', uuid=report.uuid)

    # Export download
    if run.is_export:
        if not run.export_path or not os.path.exists(run.export_path):
            messages.error(request, "The exported file has expired. Please run the report again.")
            return redirect('reporting:report_detail', uuid=report.uuid)
        response = FileResponse(
            open(run.export_path, 'rb'),
            content_type=run.export_content_type or 'application/octet-stream',
        )
        response['Content-Disposition'] = f'attachment; filename="{run.export_filename or "report"}"'
        return response

    # On-screen HTML results, rendered from the persisted rows.
    if not run.result_path or not os.path.exists(run.result_path):
        messages.error(request, "These results have expired. Please run the report again.")
        return redirect('reporting:report_detail', uuid=report.uuid)
    with open(run.result_path) as fh:
        data = json.load(fh)

    runtime_filters = report.filters.filter(prompt_at_runtime=True)
    return render(request, 'reporting/report_results.html', {
        'report': report,
        'fields': report.get_fields(),
        'data': data,
        'filter_values': run.filter_values,
        'runtime_filters': runtime_filters,
        'presentation_choices': Report.PRESENTATION_CHOICES if report.allow_presentation_choice else None,
    })


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
@require_http_methods(["GET", "POST"])
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