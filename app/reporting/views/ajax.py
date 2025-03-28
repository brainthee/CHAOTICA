from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import get_object_or_404
import json

from ..models import (
    DataArea, DataField, FilterType, Report, ReportField, ReportCategory
)
from ..services.data_service import DataService
from ..utils.filter_utils import (
    get_filter_type_choices, get_dynamic_filter_values, get_filter_value_widget_type
)

@login_required
@require_GET
def get_data_area_fields(request):
    """
    Get fields for a data area
    """
    data_area_id = request.GET.get('data_area_id')
    if not data_area_id:
        return HttpResponseBadRequest('Missing data_area_id parameter')
    
    try:
        # Get fields from service (permission filtering applied there)
        fields = DataService.get_data_area_fields(data_area_id, request.user)
        
        # Format for response
        field_data = []
        for field in fields:
            field_data.append({
                'id': field.id,
                'name': field.name,
                'display_name': field.display_name,
                'field_type': field.field_type.name,
                'group': field.group or 'General',
                'field_path': field.field_path,
                'description': field.description or '',
            })
        
        # Group fields by group
        field_groups = {}
        for field in field_data:
            group = field['group']
            if group not in field_groups:
                field_groups[group] = []
            field_groups[group].append(field)
        
        # Convert to list for easier handling in JavaScript
        groups_list = []
        for group_name, group_fields in field_groups.items():
            groups_list.append({
                'name': group_name,
                'fields': group_fields
            })
        
        return JsonResponse({
            'success': True,
            'field_groups': groups_list
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_GET
def get_field_filter_types(request):
    """
    Get available filter types for a field
    """
    field_id = request.GET.get('field_id')
    if not field_id:
        return HttpResponseBadRequest('Missing field_id parameter')
    
    try:
        field = DataField.objects.get(pk=field_id)
        field_type = field.field_type.name.lower()
        
        # Get available filter types from the database
        available_filter_types = field.get_available_filter_types().order_by('display_order')
        
        # Format filter types as (id, display_label) tuples for the frontend
        filter_types = [(ft.id, ft.display_label) for ft in available_filter_types]
        
        # Get dynamic values if appropriate
        dynamic_values = get_dynamic_filter_values(field_type)
        
        return JsonResponse({
            'success': True,
            'filter_types': filter_types,
            'dynamic_values': dynamic_values,
            'field_type': field_type
        })
        
    except DataField.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Field not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_GET
def get_filter_widget(request):
    """
    Get the appropriate widget type for a filter condition
    """
    field_id = request.GET.get('field_id')
    filter_type = request.GET.get('filter_type')
    
    if not field_id or not filter_type:
        return HttpResponseBadRequest('Missing required parameters')
    
    try:
        field = DataField.objects.get(pk=field_id)
        field_type = field.field_type.name.lower()
        
        # Get widget type
        widget_type = get_filter_value_widget_type(field_type, filter_type)
        
        # For select fields, get choices
        choices = []
        if widget_type == 'select' or widget_type == 'multi_select':
            if field_type in ('foreign_key', 'many_to_many'):
                # This would need more implementation to get actual choices
                # from related models - simplified for this example
                choices = [
                    {'value': '1', 'label': 'Example Choice 1'},
                    {'value': '2', 'label': 'Example Choice 2'},
                ]
            elif field_type == 'boolean':
                choices = [
                    {'value': 'true', 'label': 'Yes'},
                    {'value': 'false', 'label': 'No'},
                ]
        
        return JsonResponse({
            'success': True,
            'widget_type': widget_type,
            'choices': choices
        })
        
    except DataField.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Field not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_GET
def get_population_filters(request):
    """
    Get available population filters for a data area
    """
    data_area_id = request.GET.get('data_area_id')
    if not data_area_id:
        return HttpResponseBadRequest('Missing data_area_id parameter')
    
    try:
        data_area = DataArea.objects.get(pk=data_area_id)
        population_options = data_area.get_available_populations()
        
        return JsonResponse({
            'success': True,
            'population_options': population_options
        })
        
    except DataArea.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Data area not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_GET
def get_related_data_areas(request):
    """
    Get data areas related to the selected one
    """
    data_area_id = request.GET.get('data_area_id')
    if not data_area_id:
        return HttpResponseBadRequest('Missing data_area_id parameter')
    
    try:
        data_area = DataArea.objects.get(pk=data_area_id)
        related_areas = data_area.get_related_areas()
        
        # Format for response
        area_data = []
        for area in related_areas:
            area_data.append({
                'id': area.id,
                'name': area.name,
                'description': area.description or '',
                'icon_class': area.icon_class or 'fa-table',
            })
        
        return JsonResponse({
            'success': True,
            'related_areas': area_data
        })
        
    except DataArea.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Data area not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_POST
def update_report_field(request, uuid):
    """
    Update a report field's properties (label, format)
    """
    field_id = request.POST.get('field_id')
    if not field_id:
        return HttpResponseBadRequest('Missing field_id parameter')
    
    try:
        report = get_object_or_404(Report, uuid=uuid)
        field = get_object_or_404(ReportField, id=field_id, report=report)
        
        # Update properties
        if 'custom_label' in request.POST:
            field.custom_label = request.POST.get('custom_label')
        
        if 'display_format' in request.POST:
            field.display_format = request.POST.get('display_format')
        
        field.save()
        
        return JsonResponse({
            'success': True,
            'field': {
                'id': field.id,
                'custom_label': field.custom_label,
                'display_format': field.display_format,
                'display_name': field.get_display_name(),
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_POST
def reorder_report_fields(request, uuid):
    """
    Reorder report fields
    """
    try:
        report = get_object_or_404(Report, uuid=uuid)
        field_order = json.loads(request.POST.get('field_order', '[]'))
        
        if not field_order:
            return HttpResponseBadRequest('Invalid field_order parameter')
        
        # Update positions
        for i, field_id in enumerate(field_order):
            try:
                field = ReportField.objects.get(id=field_id, report=report)
                field.position = i
                field.save(update_fields=['position'])
            except ReportField.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True
        })
        
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid field_order format')
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_GET
def preview_report_data(request, uuid):
    """
    Get a sample of report data for preview
    """
    try:
        report = get_object_or_404(Report, uuid=uuid)
        
        # Set a limit for the preview
        limit = int(request.GET.get('limit', 10))
        
        # Get filter values from request
        filter_values = {}
        for key, value in request.GET.items():
            if key.startswith('filter_'):
                filter_id = key[7:]  # Remove 'filter_' prefix
                filter_values[filter_id] = value
        
        # Get a sample of data
        data = DataService.get_report_data(report, request.user, filter_values)
        
        # Limit the results
        if len(data) > limit:
            data = data[:limit]
        
        # Get field info
        fields = []
        for field in report.get_fields():
            fields.append({
                'id': field.id,
                'name': field.get_display_name(),
                'field_path': field.data_field.field_path,
            })
        
        return JsonResponse({
            'success': True,
            'fields': fields,
            'data': data,
            'has_more': len(data) >= limit
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)