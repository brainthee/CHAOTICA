import json
import logging
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from formtools.wizard.views import SessionWizardView

from chaotica_utils.models import User
from jobtracker.models import Job, Phase, TimeSlot, Project, Client, Team, Skill, OrganisationalUnit
from ..forms import (
    SelectDataAreaForm, RefineDataAreaForm, SelectDataFieldsForm,
    DefineFilterForm, DefineSortOrderForm, SelectPresentationForm,
    SaveReportForm
)
from ..models import Report

logger = logging.getLogger(__name__)

# Constants for the wizard steps
REPORT_WIZARD_FORMS = {
    'select_data_area': SelectDataAreaForm,
    'refine_data_area': RefineDataAreaForm,
    'select_fields': SelectDataFieldsForm,
    'define_filters': DefineFilterForm,
    'define_sort': DefineSortOrderForm,
    'select_presentation': SelectPresentationForm,
    'save_report': SaveReportForm,
}

# Report wizard session key
REPORT_WIZARD_SESSION_KEY = 'report_wizard_data'


class ReportWizardView(LoginRequiredMixin, SessionWizardView):
    """Wizard view for creating reports"""
    form_list = [
        ('select_data_area', SelectDataAreaForm),
        ('refine_data_area', RefineDataAreaForm),
        ('select_fields', SelectDataFieldsForm),
        ('define_filters', DefineFilterForm),
        ('define_sort', DefineSortOrderForm),
        ('select_presentation', SelectPresentationForm),
        ('save_report', SaveReportForm),
    ]
    template_name = 'reporting/report_wizard.html'
    
    def get_form_kwargs(self, step=None):
        """Pass report data to the form"""
        kwargs = super().get_form_kwargs(step)
        
        # Get report data from storage
        report_data = self.get_report_data()
        
        # Add report data to form kwargs
        kwargs['report_data'] = report_data
        
        return kwargs
    
    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        
        # Add report data to context
        context['report_data'] = self.get_report_data()
        
        # Add step-specific data
        step = self.steps.current
        
        if step == 'select_fields':
            # Add available fields as JSON for the field selector widget
            available_fields = form._get_available_fields()
            context['available_fields_json'] = json.dumps(available_fields)
            
            # Add already selected fields if any
            selected_fields = context['report_data'].get('selected_fields', [])
            context['selected_fields'] = selected_fields
            
        elif step == 'define_filters':
            # Add fields data for the filter builder
            selected_fields = context['report_data'].get('selected_fields', [])
            fields_data = self.get_fields_data(selected_fields)
            context['available_fields_json'] = json.dumps(fields_data)
            
            # Add existing filters if any
            filters = context['report_data'].get('filter_conditions', [])
            context['filters_json'] = json.dumps(filters)
            
        elif step == 'define_sort':
            # Add selected fields for the sort builder
            selected_fields = context['report_data'].get('selected_fields', [])
            context['selected_fields_json'] = json.dumps(selected_fields)
            
            # Add existing sort order if any
            sort_order = context['report_data'].get('sort_order', [])
            context['sort_order_json'] = json.dumps(sort_order)
            
        elif step == 'select_presentation':
            # Add presentation-specific data if needed
            pass
            
        return context
    
    def get_report_data(self):
        """Get the report data from storage"""
        try:
            # Try to get data from the cleaned data if available
            if self.storage and hasattr(self.storage, 'data'):
                all_data = {}
                for step_name in self.steps.all:
                    if step_name in self.storage.data:
                        step_data = self.storage.get_step_data(step_name)
                        if step_data:
                            form = self.get_form(
                                step=step_name,
                                data=step_data,
                                files=self.storage.get_step_files(step_name)
                            )
                            if form.is_valid():
                                all_data.update(form.cleaned_data)
                return all_data
            
        except Exception as e:
            # Log the error but continue with session data
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error getting wizard cleaned data: {e}", exc_info=True)
            
        # Fall back to session storage
        return self.request.session.get(REPORT_WIZARD_SESSION_KEY, {})
    
    def get_fields_data(self, selected_fields):
        """Get field data for selected fields"""
        # Convert selected fields to a more usable format for the filter builder
        data_area = self.get_report_data().get('data_area')
        
        # This would need to be customized based on your models and fields
        fields_data = []
        
        # Example: For User model fields
        if data_area == 'user':
            fields_data = [
                {
                    'name': 'email',
                    'label': 'Email',
                    'type': 'string',
                    'operators': ['equals', 'contains', 'starts_with', 'ends_with'],
                },
                {
                    'name': 'first_name',
                    'label': 'First Name',
                    'type': 'string',
                    'operators': ['equals', 'contains', 'starts_with', 'ends_with'],
                },
                {
                    'name': 'last_name',
                    'label': 'Last Name',
                    'type': 'string',
                    'operators': ['equals', 'contains', 'starts_with', 'ends_with'],
                },
                {
                    'name': 'is_active',
                    'label': 'Active',
                    'type': 'boolean',
                    'operators': ['equals'],
                },
                {
                    'name': 'date_joined',
                    'label': 'Date Joined',
                    'type': 'date',
                    'operators': ['equals', 'greater_than', 'less_than', 'between'],
                },
            ]
        # Example: For Job model fields
        elif data_area == 'job':
            fields_data = [
                {
                    'name': 'title',
                    'label': 'Title',
                    'type': 'string',
                    'operators': ['equals', 'contains', 'starts_with', 'ends_with'],
                },
                {
                    'name': 'status',
                    'label': 'Status',
                    'type': 'integer',
                    'operators': ['equals', 'in'],
                    'values': [
                        {'value': 0, 'label': 'Untracked'},
                        {'value': 1, 'label': 'Pending'},
                        {'value': 2, 'label': 'In Progress'},
                        {'value': 3, 'label': 'Complete'},
                        {'value': 4, 'label': 'Deleted'},
                        {'value': 5, 'label': 'Archived'},
                    ],
                },
                {
                    'name': 'created_at',
                    'label': 'Created Date',
                    'type': 'date',
                    'operators': ['equals', 'greater_than', 'less_than', 'between'],
                },
                {
                    'name': 'client__name',
                    'label': 'Client Name',
                    'type': 'string',
                    'operators': ['equals', 'contains', 'starts_with', 'ends_with'],
                },
            ]
            
        # More data areas could be added as needed
        
        return fields_data
    
    def process_step(self, form):
        """Process the form for the current step"""
        # Get the cleaned data
        cleaned_data = form.cleaned_data
        
        # Get existing report data
        report_data = self.get_report_data()
        
        # Update with new data
        report_data.update(cleaned_data)
        
        # Special handling for some steps
        step = self.steps.current
        
        if step == 'select_data_area':
            # Reset dependent fields when data area changes
            if 'data_area' in cleaned_data:
                # Clear population filters, selected fields, etc.
                keys_to_clear = [
                    'population_type', 'organisational_unit', 'client', 'unit',
                    'selected_fields', 'filter_conditions', 'sort_order'
                ]
                for key in keys_to_clear:
                    if key in report_data:
                        del report_data[key]
        
        elif step == 'refine_data_area':
            # Convert population options to JSON format for storage
            population_filter = {}
            if 'population_type' in cleaned_data:
                population_filter['type'] = cleaned_data['population_type']
                
                # Add additional data based on population type
                if cleaned_data['population_type'] == 'within_orgunit' and cleaned_data.get('organisational_unit'):
                    population_filter['organisational_unit_id'] = cleaned_data['organisational_unit'].id
                    
                elif cleaned_data['population_type'] == 'by_client' and cleaned_data.get('client'):
                    population_filter['client_id'] = cleaned_data['client'].id
                    
                elif cleaned_data['population_type'] == 'by_unit' and cleaned_data.get('unit'):
                    population_filter['unit_id'] = cleaned_data['unit'].id
            
            # Store in report data
            report_data['population_filter'] = population_filter
            
        elif step == 'select_fields':
            # Convert field selections to structured format
            if 'selected_fields' in cleaned_data:
                selected_fields = []
                
                for field_id in cleaned_data['selected_fields']:
                    # Parse the field ID which might contain type information
                    parts = field_id.split(':', 1)
                    field_name = parts[0]
                    field_type = parts[1] if len(parts) > 1 else 'direct'
                    
                    field_def = {
                        'name': field_name,
                        'type': field_type,
                        'display_name': field_name.replace('__', ' ').replace('_', ' ').title()
                    }
                    
                    # Add additional properties for special field types
                    if field_type == 'concat':
                        # Assume fields with '_' could be concatenated
                        field_def['source_fields'] = field_name.split('__')
                        field_def['separator'] = ' '
                    
                    selected_fields.append(field_def)
                
                # Store structured field definitions
                report_data['selected_fields'] = selected_fields
        
        elif step == 'define_filters':
            # Get filter conditions from the request data
            filter_data = self.request.POST.get('filter_data', '{}')
            try:
                filter_conditions = json.loads(filter_data)
                report_data['filter_conditions'] = filter_conditions
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Error parsing filter data: {e}")
                report_data['filter_conditions'] = []
                
        elif step == 'define_sort':
            # Get sort order from the request data
            sort_data = self.request.POST.get('sort_data', '[]')
            try:
                sort_order = json.loads(sort_data)
                report_data['sort_order'] = sort_order
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Error parsing sort data: {e}")
                report_data['sort_order'] = []
        
        # Store updated report data in session
        self.request.session[REPORT_WIZARD_SESSION_KEY] = report_data
        
        return super().process_step(form)
    
    def done(self, form_list, **kwargs):
        """Final processing to save the report"""
        # Get all form data
        report_data = self.get_report_data()
        
        # Create the Report object
        report = Report(
            name=report_data.get('name', 'Unnamed Report'),
            description=report_data.get('description', ''),
            is_private=report_data.get('is_private', True),
            created_by=self.request.user,
            
            # Report definition
            data_area=report_data.get('data_area'),
            population_filter=report_data.get('population_filter', {}),
            selected_fields=report_data.get('selected_fields', []),
            filter_conditions=report_data.get('filter_conditions', []),
            sort_order=report_data.get('sort_order', []),
            
            # Presentation options
            default_presentation=report_data.get('presentation_type', 'excel'),
            allow_runtime_presentation_choice=report_data.get('allow_choice_at_runtime', True),
            presentation_options={
                'excel': {
                    'template': report_data.get('excel_template', 'standard')
                }
                # Additional presentation options could be added here
            }
        )
        
        # Set category if selected
        if report_data.get('category'):
            report.category = report_data.get('category')
            
        # Save the report
        report.save()
        
        # Clear session data
        if REPORT_WIZARD_SESSION_KEY in self.request.session:
            del self.request.session[REPORT_WIZARD_SESSION_KEY]
            
        # Show success message
        messages.success(self.request, _('Report created successfully.'))
        
        # Redirect to the report detail page
        return redirect('reporting:report_detail', pk=report.pk)


# Individual report wizard step views (for direct access to specific steps)
@login_required
def report_wizard_step1(request):
    """Redirect to the first step of the report wizard"""
    # Clear any existing wizard data
    if REPORT_WIZARD_SESSION_KEY in request.session:
        del request.session[REPORT_WIZARD_SESSION_KEY]
    
    return redirect('reporting:report_wizard')

@login_required
def report_wizard_step2(request):
    """Redirect to the second step of the report wizard"""
    # Check if we have data for step 1
    report_data = request.session.get(REPORT_WIZARD_SESSION_KEY, {})
    
    if 'data_area' not in report_data:
        messages.warning(request, _('Please complete Step 1 first.'))
        return redirect('reporting:report_wizard')
    
    return redirect('reporting:report_wizard', step='refine_data_area')

@login_required
def report_wizard_step3(request):
    """Redirect to the third step of the report wizard"""
    # Check if we have data for previous steps
    report_data = request.session.get(REPORT_WIZARD_SESSION_KEY, {})
    
    if 'data_area' not in report_data:
        messages.warning(request, _('Please complete previous steps first.'))
        return redirect('reporting:report_wizard')
    
    return redirect('reporting:report_wizard', step='select_fields')

@login_required
def report_wizard_step4(request):
    """Redirect to the fourth step of the report wizard"""
    report_data = request.session.get(REPORT_WIZARD_SESSION_KEY, {})
    
    if 'selected_fields' not in report_data or not report_data['selected_fields']:
        messages.warning(request, _('Please select fields first.'))
        return redirect('reporting:report_wizard', step='select_fields')
    
    return redirect('reporting:report_wizard', step='define_filters')

@login_required
def report_wizard_step5(request):
    """Redirect to the fifth step of the report wizard"""
    return redirect('reporting:report_wizard', step='define_sort')

@login_required
def report_wizard_step6(request):
    """Redirect to the sixth step of the report wizard"""
    return redirect('reporting:report_wizard', step='select_presentation')