import json
import logging
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST

from ..models import Report
from ..engine import ReportEngine

logger = logging.getLogger(__name__)


@login_required
@require_GET
def api_field_data(request, data_area):
    """API endpoint to get field data for a data area"""
    # This would return field metadata for the field selector
    # Simplified example:
    field_groups = []
    
    if data_area == 'user':
        field_groups = [
            {
                'name': 'User Information',
                'fields': [
                    {'name': 'id', 'type': 'direct', 'verbose_name': 'ID'},
                    {'name': 'email', 'type': 'direct', 'verbose_name': 'Email'},
                    {'name': 'first_name', 'type': 'direct', 'verbose_name': 'First Name'},
                    {'name': 'last_name', 'type': 'direct', 'verbose_name': 'Last Name'},
                    {'name': 'is_active', 'type': 'direct', 'verbose_name': 'Active'},
                    {'name': 'date_joined', 'type': 'direct', 'verbose_name': 'Date Joined'},
                ]
            },
            {
                'name': 'Related Information',
                'fields': [
                    {'name': 'manager__first_name', 'type': 'related', 'verbose_name': 'Manager First Name'},
                    {'name': 'manager__last_name', 'type': 'related', 'verbose_name': 'Manager Last Name'},
                ]
            }
        ]
    elif data_area == 'job':
        field_groups = [
            {
                'name': 'Job Information',
                'fields': [
                    {'name': 'id', 'type': 'direct', 'verbose_name': 'ID'},
                    {'name': 'title', 'type': 'direct', 'verbose_name': 'Title'},
                    {'name': 'status', 'type': 'direct', 'verbose_name': 'Status'},
                    {'name': 'created_at', 'type': 'direct', 'verbose_name': 'Created Date'},
                ]
            },
            {
                'name': 'Client Information',
                'fields': [
                    {'name': 'client__name', 'type': 'related', 'verbose_name': 'Client Name'},
                    {'name': 'client__industry', 'type': 'related', 'verbose_name': 'Client Industry'},
                ]
            }
        ]
    
    return JsonResponse({'field_groups': field_groups})


@login_required
@require_POST
def api_report_preview(request, pk):
    """API endpoint to get a preview of the report data"""
    report = get_object_or_404(Report, pk=pk)
    
    # Check if user has access
    if report.is_private and report.created_by != request.user:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        # Extract runtime parameters if any
        params = {}
        
        # Extract filter prompt values
        for key, value in request.POST.items():
            if key.startswith('prompt_'):
                params[key] = value
        
        # Execute report with limit
        report_engine = ReportEngine(report, request.user)
        report_data = report_engine.execute(params)
        
        # Limit to 10 rows for preview
        if 'data' in report_data and len(report_data['data']) > 10:
            report_data['data'] = report_data['data'][:10]
            report_data['metadata']['preview'] = True
            report_data['metadata']['preview_count'] = 10
            report_data['metadata']['total_count'] = len(report_data['data'])
        
        return JsonResponse(report_data)
        
    except Exception as e:
        logger.error(f"Error generating report preview: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)