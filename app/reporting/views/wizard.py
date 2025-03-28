import json
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST

from ..forms import (
    SelectDataAreaForm, SelectFieldsForm, FilterConditionForm,
    DefineFiltersForm, DefineSortOrderForm, DefinePresentationForm,
    SaveReportForm
)
from ..models import (
    Report, ReportField, ReportFilter, ReportSort,
    DataArea, DataField, FilterType
)
from ..services.session_service import SessionService
from ..services.data_service import DataService
from ..permissions import can_create_report, can_edit_report

@login_required
def wizard_start(request, report_uuid=None):
    """
    Start (or resume) the report wizard
    """
    # Check if editing an existing report
    report = None
    if report_uuid:
        report = get_object_or_404(Report, uuid=report_uuid)
        if not can_edit_report(request.user, report):
            messages.error(request, "You don't have permission to edit this report.")
            return redirect('reporting:report_list')
    else:
        # Check if user can create reports
        if not can_create_report(request.user):
            messages.error(request, "You don't have permission to create reports.")
            return redirect('reporting:report_list')
    
    # Reset the wizard session
    SessionService.reset_wizard(request)
    
    # If editing, load report data into session
    if report:
        # Set basic report info
        wizard_data = {
            'report_name': report.name,
            'report_description': report.description,
            'is_private': report.is_private,
            'report_id': str(report.uuid),
        }
        
        # Data area
        wizard_data['data_area'] = {
            'data_area_id': report.data_area.id,
            'population_filter': report.population_filter,
        }
        
        # Fields
        wizard_data['fields'] = {
            'selected_fields': [
                {
                    'id': field.id,
                    'field_id': field.data_field.id,
                    'position': field.position,
                    'custom_label': field.custom_label,
                    'display_format': field.display_format,
                } for field in report.get_fields()
            ]
        }
        
        # Filters
        wizard_data['filters'] = {
            'filter_conditions': [
                {
                    'id': filter_obj.id,
                    'field_id': filter_obj.data_field.id,
                    'filter_type_id': filter_obj.filter_type.id,
                    'value': filter_obj.value,
                    'prompt_at_runtime': filter_obj.prompt_at_runtime,
                    'prompt_text': filter_obj.prompt_text,
                    'parent_filter_id': filter_obj.parent_filter_id,
                    'operator': filter_obj.operator,
                    'position': filter_obj.position,
                } for filter_obj in report.get_filters()
            ]
        }
        
        # Sorts
        wizard_data['sorts'] = {
            'sort_fields': [
                {
                    'id': sort.id,
                    'field_id': sort.data_field.id,
                    'direction': sort.direction,
                    'position': sort.position,
                } for sort in report.get_sorts()
            ]
        }
        
        # Presentation
        wizard_data['presentation'] = {
            'presentation_type': report.presentation_type,
            'presentation_options': report.presentation_options,
            'allow_presentation_choice': report.allow_presentation_choice,
        }
        
        # Save to session
        SessionService.save_wizard_data(request, wizard_data)
        
        # Redirect to appropriate step
        return redirect('reporting:wizard_select_data_area')
    else:
        # Start with a blank report
        return redirect('reporting:wizard_select_data_area')


@login_required
def wizard_select_data_area(request):
    """
    First step of wizard: select the data area
    """
    # Get existing data from session
    wizard_data = SessionService.get_wizard_data(request)
    data_area_data = wizard_data.get('data_area', {})
    
    # Create form with session data
    initial_data = {
        'data_area': data_area_data.get('data_area_id'),
        'population_filter': data_area_data.get('population_filter'),
    }
    
    form = SelectDataAreaForm(request.POST or None, initial=initial_data, user=request.user)
    
    if request.method == 'POST' and form.is_valid():
        # Save form data to session
        data_area_id = form.cleaned_data['data_area'].id
        population_filter = form.cleaned_data['population_filter']
        
        SessionService.update_wizard_step(request, 'data_area', {
            'data_area_id': data_area_id,
            'population_filter': population_filter,
        })
        
        # Continue to next step
        return redirect('reporting:wizard_select_fields')
    
    # Get all available data areas for display
    data_areas = DataService.get_available_data_areas(request.user)
    
    return render(request, 'reporting/wizard/select_data_area.html', {
        'form': form,
        'data_areas': data_areas,
        'wizard_step': 'data_area',
    })


@login_required
def wizard_select_fields(request):
    """
    Second step of wizard: select the fields
    """
    # Check if we have a data area selected
    wizard_data = SessionService.get_wizard_data(request)
    data_area_data = wizard_data.get('data_area', {})

    from pprint import pprint
    pprint(wizard_data)
    
    if not data_area_data or 'data_area_id' not in data_area_data:
        messages.error(request, "Please select a data area first.")
        return redirect('reporting:wizard_select_data_area')
    
    # Get the data area
    data_area_id = data_area_data['data_area_id']
    try:
        data_area = DataArea.objects.get(pk=data_area_id)
    except DataArea.DoesNotExist:
        messages.error(request, "Invalid data area selected.")
        return redirect('reporting:wizard_select_data_area')
    
    # Get fields from session
    fields_data = wizard_data.get('fields', {})
    selected_fields = fields_data.get('selected_fields', [])
    
    # Create form
    form = SelectFieldsForm(request.POST or None, data_area=data_area, user=request.user)
    
    if request.method == 'POST' and form.is_valid():
        # Get selected fields
        field_objects = form.get_selected_fields()
        
        # Save to session
        field_data = []
        for i, field in enumerate(field_objects):
            # Look up existing field data if previously selected
            existing_data = next(
                (f for f in selected_fields if f.get('field_id') == field.id),
                {}
            )
            
            field_data.append({
                'field_id': field.id,
                'position': existing_data.get('position', i),
                'custom_label': existing_data.get('custom_label', ''),
                'display_format': existing_data.get('display_format', ''),
            })
        
        SessionService.update_wizard_step(request, 'fields', {
            'selected_fields': field_data,
        })
        
        # Continue to next step
        return redirect('reporting:wizard_define_filters')
    
    # If we have selected fields from session, set initial values
    if selected_fields:
        # Convert to a dict of field IDs grouped by group name
        initial_fields = {}
        for field_data in selected_fields:
            field_id = field_data.get('field_id')
            try:
                field = DataField.objects.get(pk=field_id)
                group_name = field.group or 'General'
                if f'group_{group_name}' not in initial_fields:
                    initial_fields[f'group_{group_name}'] = []
                initial_fields[f'group_{group_name}'].append(field_id)
            except DataField.DoesNotExist:
                continue
        
        # Set initial values for each group field
        for field_name, field_ids in initial_fields.items():
            if field_name in form.fields:
                form.fields[field_name].initial = field_ids
    
    return render(request, 'reporting/wizard/select_fields.html', {
        'form': form,
        'data_area': data_area,
        'wizard_step': 'fields',
    })


@login_required
def wizard_define_filters(request):
    """
    Third step of wizard: define filters
    """
    # Check if we have fields selected
    wizard_data = SessionService.get_wizard_data(request)
    data_area_data = wizard_data.get('data_area', {})
    fields_data = wizard_data.get('fields', {})
    
    if not data_area_data or 'data_area_id' not in data_area_data:
        messages.error(request, "Please select a data area first.")
        return redirect('reporting:wizard_select_data_area')
    
    if not fields_data or 'selected_fields' not in fields_data or not fields_data['selected_fields']:
        messages.error(request, "Please select at least one field first.")
        return redirect('reporting:wizard_select_fields')
    
    # Get the data area
    data_area_id = data_area_data['data_area_id']
    try:
        data_area = DataArea.objects.get(pk=data_area_id)
    except DataArea.DoesNotExist:
        messages.error(request, "Invalid data area selected.")
        return redirect('reporting:wizard_select_data_area')
    
    # Get filter conditions from session
    filters_data = wizard_data.get('filters', {})
    filter_conditions = filters_data.get('filter_conditions', [])
    
    # Create form
    form = DefineFiltersForm(request.POST or None, data_area=data_area, initial={
        'filter_conditions': json.dumps(filter_conditions),
    })
    
    if request.method == 'POST' and form.is_valid():
        # Get filter conditions from form
        filter_conditions_json = form.cleaned_data['filter_conditions']
        filter_conditions = json.loads(filter_conditions_json) if filter_conditions_json else []
        
        # Save to session
        SessionService.update_wizard_step(request, 'filters', {
            'filter_conditions': filter_conditions,
        })
        
        # Continue to next step
        return redirect('reporting:wizard_define_sort')
    
    # Get available fields for filters (all fields from data area)
    available_fields = DataField.objects.filter(
        data_area=data_area,
        is_available=True
    ).order_by('group', 'display_name')
    
    # Filter out sensitive fields based on permissions
    if not request.user.is_superuser:
        restricted_fields = []
        for field in available_fields:
            if field.is_sensitive and field.requires_permission:
                if not request.user.has_perm(field.requires_permission):
                    restricted_fields.append(field.id)
        
        if restricted_fields:
            available_fields = available_fields.exclude(id__in=restricted_fields)
    
    # Get available filter types
    filter_types = FilterType.objects.filter(is_available=True).order_by('display_order')
    
    return render(request, 'reporting/wizard/define_filters.html', {
        'form': form,
        'data_area': data_area,
        'available_fields': available_fields,
        'filter_types': filter_types,
        'filter_conditions': filter_conditions,
        'wizard_step': 'filters',
    })


@login_required
def wizard_define_sort(request):
    """
    Fourth step of wizard: define sort order
    """
    # Check if we have fields selected
    wizard_data = SessionService.get_wizard_data(request)
    data_area_data = wizard_data.get('data_area', {})
    fields_data = wizard_data.get('fields', {})
    
    if not data_area_data or 'data_area_id' not in data_area_data:
        messages.error(request, "Please select a data area first.")
        return redirect('reporting:wizard_select_data_area')
    
    if not fields_data or 'selected_fields' not in fields_data or not fields_data['selected_fields']:
        messages.error(request, "Please select at least one field first.")
        return redirect('reporting:wizard_select_fields')
    
    # Get the data area
    data_area_id = data_area_data['data_area_id']
    try:
        data_area = DataArea.objects.get(pk=data_area_id)
    except DataArea.DoesNotExist:
        messages.error(request, "Invalid data area selected.")
        return redirect('reporting:wizard_select_data_area')
    
    # Get selected fields
    selected_fields_data = fields_data['selected_fields']
    selected_field_ids = [f['field_id'] for f in selected_fields_data]
    selected_fields = DataField.objects.filter(id__in=selected_field_ids)
    
    # Get sort fields from session
    sorts_data = wizard_data.get('sorts', {})
    sort_fields = sorts_data.get('sort_fields', [])
    
    # Create form
    form = DefineSortOrderForm(request.POST or None, data_area=data_area, fields=selected_fields)
    
    if request.method == 'POST' and form.is_valid():
        # Build sort fields list from form data
        new_sort_fields = []
        
        for i, field in enumerate(selected_fields):
            field_id = field.id
            
            # Check if this field is included in the sort
            if form.cleaned_data.get(f'sort_field_{field_id}', False):
                direction = form.cleaned_data.get(f'sort_direction_{field_id}', 'asc')
                position = form.cleaned_data.get(f'sort_position_{field_id}', i)
                
                new_sort_fields.append({
                    'field_id': field_id,
                    'direction': direction,
                    'position': position,
                })
        
        # Sort by position
        new_sort_fields.sort(key=lambda x: x['position'])
        
        # Save to session
        SessionService.update_wizard_step(request, 'sorts', {
            'sort_fields': new_sort_fields,
        })
        
        # Continue to next step
        return redirect('reporting:wizard_define_presentation')
    
    # If we have sort fields from session, set initial values
    if sort_fields:
        for sort_data in sort_fields:
            field_id = sort_data.get('field_id')
            if f'sort_field_{field_id}' in form.fields:
                form.fields[f'sort_field_{field_id}'].initial = True
                form.fields[f'sort_direction_{field_id}'].initial = sort_data.get('direction', 'asc')
                form.fields[f'sort_position_{field_id}'].initial = sort_data.get('position', 0)
    
    return render(request, 'reporting/wizard/define_sort.html', {
        'form': form,
        'data_area': data_area,
        'selected_fields': selected_fields,
        'wizard_step': 'sorts',
    })


@login_required
def wizard_define_presentation(request):
    """
    Fifth step of wizard: define presentation options
    """
    # Check if we have fields selected
    wizard_data = SessionService.get_wizard_data(request)
    data_area_data = wizard_data.get('data_area', {})
    fields_data = wizard_data.get('fields', {})
    
    if not data_area_data or 'data_area_id' not in data_area_data:
        messages.error(request, "Please select a data area first.")
        return redirect('reporting:wizard_select_data_area')
    
    if not fields_data or 'selected_fields' not in fields_data or not fields_data['selected_fields']:
        messages.error(request, "Please select at least one field first.")
        return redirect('reporting:wizard_select_fields')
    
    # Get presentation options from session
    presentation_data = wizard_data.get('presentation', {})
    
    # Set initial form data
    initial_data = {
        'presentation_type': presentation_data.get('presentation_type', 'excel'),
        'allow_presentation_choice': presentation_data.get('allow_presentation_choice', False),
    }
    
    # Add format-specific options
    presentation_options = presentation_data.get('presentation_options', {})
    if 'excel_group_records' in presentation_options:
        initial_data['excel_group_records'] = presentation_options['excel_group_records']
    if 'excel_freeze_columns' in presentation_options:
        initial_data['excel_freeze_columns'] = presentation_options['excel_freeze_columns']
    if 'pdf_orientation' in presentation_options:
        initial_data['pdf_orientation'] = presentation_options['pdf_orientation']
    if 'pdf_paper_size' in presentation_options:
        initial_data['pdf_paper_size'] = presentation_options['pdf_paper_size']
    if 'html_include_styling' in presentation_options:
        initial_data['html_include_styling'] = presentation_options['html_include_styling']
    if 'word_template' in presentation_options:
        initial_data['word_template'] = presentation_options['word_template']
    if 'text_delimiter' in presentation_options:
        initial_data['text_delimiter'] = presentation_options['text_delimiter']
    
    # Create form
    form = DefinePresentationForm(request.POST or None, initial=initial_data)
    
    if request.method == 'POST' and form.is_valid():
        # Get basic presentation options
        presentation_type = form.cleaned_data['presentation_type']
        allow_presentation_choice = form.cleaned_data['allow_presentation_choice']
        
        # Build presentation options based on the selected type
        presentation_options = {}
        
        if presentation_type == 'excel':
            presentation_options.update({
                'excel_group_records': form.cleaned_data.get('excel_group_records', 0),
                'excel_freeze_columns': form.cleaned_data.get('excel_freeze_columns', 0),
            })
        elif presentation_type == 'pdf':
            presentation_options.update({
                'pdf_orientation': form.cleaned_data.get('pdf_orientation', 'landscape'),
                'pdf_paper_size': form.cleaned_data.get('pdf_paper_size', 'a4'),
            })
        elif presentation_type == 'html':
            presentation_options.update({
                'html_include_styling': form.cleaned_data.get('html_include_styling', True),
            })
        elif presentation_type == 'word':
            presentation_options.update({
                'word_template': form.cleaned_data.get('word_template', 'standard_landscape'),
            })
        elif presentation_type == 'text':
            presentation_options.update({
                'text_delimiter': form.cleaned_data.get('text_delimiter', 'tab'),
            })
        
        # Save to session
        SessionService.update_wizard_step(request, 'presentation', {
            'presentation_type': presentation_type,
            'presentation_options': presentation_options,
            'allow_presentation_choice': allow_presentation_choice,
        })
        
        # Continue to next step
        return redirect('reporting:wizard_preview')
    
    return render(request, 'reporting/wizard/define_presentation.html', {
        'form': form,
        'wizard_step': 'presentation',
    })


@login_required
def wizard_preview(request):
    """
    Final step of wizard: preview and save the report
    """
    # Check if we have all required data
    wizard_data = SessionService.get_wizard_data(request)
    data_area_data = wizard_data.get('data_area', {})
    fields_data = wizard_data.get('fields', {})
    
    if not data_area_data or 'data_area_id' not in data_area_data:
        messages.error(request, "Please select a data area first.")
        return redirect('reporting:wizard_select_data_area')
    
    if not fields_data or 'selected_fields' not in fields_data or not fields_data['selected_fields']:
        messages.error(request, "Please select at least one field first.")
        return redirect('reporting:wizard_select_fields')
    
    # Get data for preview
    data_area_id = data_area_data['data_area_id']
    data_area = DataArea.objects.get(pk=data_area_id)
    
    # Get selected fields
    selected_fields_data = fields_data.get('selected_fields', [])
    selected_field_ids = [f['field_id'] for f in selected_fields_data]
    selected_fields = DataField.objects.filter(id__in=selected_field_ids)
    
    # Get filter conditions
    filters_data = wizard_data.get('filters', {})
    filter_conditions = filters_data.get('filter_conditions', [])
    
    # Get sort fields
    sorts_data = wizard_data.get('sorts', {})
    sort_fields = sorts_data.get('sort_fields', [])
    
    # Create save form with initial data
    form = SaveReportForm(request.POST or None, initial={
        'name': wizard_data.get('report_name', ''),
        'description': wizard_data.get('report_description', ''),
        'is_private': wizard_data.get('is_private', True),
    })
    
    if request.method == 'POST' and form.is_valid():
        # Create or update the report
        report_uuid = wizard_data.get('report_id')
        
        if report_uuid:
            # Updating existing report
            try:
                report = Report.objects.get(uuid=report_uuid)
                if not can_edit_report(request.user, report):
                    messages.error(request, "You don't have permission to edit this report.")
                    return redirect('reporting:report_list')
            except Report.DoesNotExist:
                report = None
        else:
            report = None
        
        # Create new report if needed
        if not report:
            report = Report(owner=request.user)
        
        # Update basic report info
        report.name = form.cleaned_data['name']
        report.description = form.cleaned_data['description']
        report.category = form.cleaned_data['category']
        report.is_private = form.cleaned_data['is_private']
        
        # Set data area
        report.data_area_id = data_area_id
        report.population_filter = data_area_data.get('population_filter')
        
        # Set presentation options
        presentation_data = wizard_data.get('presentation', {})
        report.presentation_type = presentation_data.get('presentation_type', 'excel')
        report.presentation_options = presentation_data.get('presentation_options', {})
        report.allow_presentation_choice = presentation_data.get('allow_presentation_choice', False)
        
        # Save the report
        report.save()
        
        # Clear existing fields, filters, and sorts
        report.fields.all().delete()
        report.filters.all().delete()
        report.sorts.all().delete()
        
        # Create report fields
        for i, field_data in enumerate(selected_fields_data):
            field_id = field_data.get('field_id')
            try:
                data_field = DataField.objects.get(pk=field_id)
                report_field = ReportField(
                    report=report,
                    data_field=data_field,
                    position=i,
                    custom_label=field_data.get('custom_label', ''),
                    display_format=field_data.get('display_format', ''),
                )
                report_field.save()
            except DataField.DoesNotExist:
                pass
        
        # Create filter conditions
        for i, filter_data in enumerate(filter_conditions):
            field_id = filter_data.get('field_id')
            filter_type_id = filter_data.get('filter_type_id')
            
            try:
                data_field = DataField.objects.get(pk=field_id)
                filter_type = FilterType.objects.get(pk=filter_type_id)
                
                parent_filter_id = filter_data.get('parent_filter_id')
                parent_filter = None
                if parent_filter_id:
                    try:
                        parent_filter = ReportFilter.objects.get(pk=parent_filter_id, report=report)
                    except ReportFilter.DoesNotExist:
                        pass
                
                report_filter = ReportFilter(
                    report=report,
                    data_field=data_field,
                    filter_type=filter_type,
                    value=filter_data.get('value'),
                    prompt_at_runtime=filter_data.get('prompt_at_runtime', False),
                    prompt_text=filter_data.get('prompt_text', ''),
                    parent_filter=parent_filter,
                    operator=filter_data.get('operator', 'and'),
                    position=i,
                )
                report_filter.save()
            except (DataField.DoesNotExist, FilterType.DoesNotExist):
                pass
        
        # Create sort fields
        for i, sort_data in enumerate(sort_fields):
            field_id = sort_data.get('field_id')
            try:
                data_field = DataField.objects.get(pk=field_id)
                report_sort = ReportSort(
                    report=report,
                    data_field=data_field,
                    direction=sort_data.get('direction', 'asc'),
                    position=i,
                )
                report_sort.save()
            except DataField.DoesNotExist:
                pass
        
        # Show success message
        action = "updated" if report_uuid else "created"
        messages.success(request, f"Report {action} successfully.")
        
        # Clear wizard session
        SessionService.reset_wizard(request)
        
        # Redirect to view report
        return redirect('reporting:report_detail', uuid=report.uuid)
    
    # Generate a sample of data for preview
    # This is a simplified version - a real implementation would use DataService
    sample_data = []
    
    return render(request, 'reporting/wizard/preview.html', {
        'form': form,
        'data_area': data_area,
        'selected_fields': selected_fields,
        'filter_conditions': filter_conditions,
        'sort_fields': sort_fields,
        'presentation_type': wizard_data.get('presentation', {}).get('presentation_type', 'excel'),
        'sample_data': sample_data,
        'wizard_step': 'preview',
    })


@login_required
@require_POST
def wizard_field_customize(request):
    """
    AJAX endpoint to customize a field
    """
    # Get field info from request
    field_id = request.POST.get('field_id')
    custom_label = request.POST.get('custom_label', '')
    display_format = request.POST.get('display_format', '')
    
    # Get wizard data from session
    wizard_data = SessionService.get_wizard_data(request)
    fields_data = wizard_data.get('fields', {})
    selected_fields = fields_data.get('selected_fields', [])
    
    # Find the field and update it
    updated = False
    for field in selected_fields:
        if str(field.get('field_id')) == str(field_id):
            field['custom_label'] = custom_label
            field['display_format'] = display_format
            updated = True
            break
    
    # If field not found, add it
    if not updated:
        selected_fields.append({
            'field_id': field_id,
            'position': len(selected_fields),
            'custom_label': custom_label,
            'display_format': display_format,
        })
    
    # Save back to session
    fields_data['selected_fields'] = selected_fields
    SessionService.update_wizard_step(request, 'fields', fields_data)
    
    return JsonResponse({'success': True})


@login_required
@require_POST
def wizard_field_reorder(request):
    """
    AJAX endpoint to reorder fields
    """
    # Get field order from request
    try:
        field_order = json.loads(request.POST.get('field_order', '[]'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid field order")
    
    # Get wizard data from session
    wizard_data = SessionService.get_wizard_data(request)
    fields_data = wizard_data.get('fields', {})
    selected_fields = fields_data.get('selected_fields', [])
    
    # Create a mapping of field_id to field data
    field_map = {str(field.get('field_id')): field for field in selected_fields}
    
    # Create new ordered list
    new_fields = []
    for i, field_id in enumerate(field_order):
        if field_id in field_map:
            field = field_map[field_id]
            field['position'] = i
            new_fields.append(field)
    
    # Save back to session
    fields_data['selected_fields'] = new_fields
    SessionService.update_wizard_step(request, 'fields', fields_data)
    
    return JsonResponse({'success': True})


@login_required
@require_POST
def wizard_cancel(request):
    """
    Cancel the wizard and clear session data
    """
    # Clear wizard session
    SessionService.reset_wizard(request)
    
    # Redirect to reports list
    return redirect('reporting:report_list')