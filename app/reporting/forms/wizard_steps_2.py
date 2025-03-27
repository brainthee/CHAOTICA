from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.layout import Layout, Submit, Div, Field, HTML, ButtonHolder
from django.db.models.functions import Lower

from .base import ReportDesignerBaseForm
from chaotica_utils.models import User, LeaveRequest
from jobtracker.models import (
    Job, Phase, TimeSlot, Project, Client, Team, Skill, 
    OrganisationalUnit
)

class SelectDataFieldsForm(ReportDesignerBaseForm):
    """Form for selecting data fields (columns)"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get the available fields based on the data area
        self.available_fields = self._get_available_fields()
        
        # No regular form fields here - we'll use a custom widget
        # to allow selecting fields from a hierarchical structure
        
        self.helper.layout = Layout(
            HTML('<h3>Step 3: Select Data Fields</h3>'),
            HTML('<p>Choose the data fields (columns) to include in your report.</p>'),
            HTML('<div id="field-selector" data-available-fields=\'{{ available_fields_json }}\'></div>'),
            ButtonHolder(
                HTML('<a href="{% url "reporting:report_wizard_step2" %}" class="btn btn-default">Back</a>'),
                Submit('next', _('Next Step'), css_class='btn-primary')
            )
        )

    def _get_available_fields(self):
        """Get available fields based on the selected data area"""
        data_area = self.report_data.get('data_area')
        field_groups = []
        
        # Map data areas to models
        model_map = {
            'user': User,
            'job': Job,
            'phase': Phase,
            'timeslot': TimeSlot,
            'project': Project,
            'client': Client,
            'team': Team,
            'skill': Skill,
            'organisational_unit': OrganisationalUnit,
            'leave_request': LeaveRequest,  # Add other models as needed
        }
        
        model = model_map.get(data_area)
        if not model:
            return field_groups
        
        # 1. Add direct fields from the primary model
        primary_fields = []
        
        # This is where you can customize which fields to include
        # For example, for User model, you might want to include specific fields:
        if data_area == 'user':
            # Define a list of fields you want to include
            include_fields = ['id', 'email', 'first_name', 'last_name', 'is_active', 
                            'date_joined', 'job_title', 'manager', 'country']
            
            for field in model._meta.get_fields():
                if field.name in include_fields:
                    primary_fields.append({
                        'name': field.name,
                        'type': 'direct',
                        'verbose_name': field.verbose_name if hasattr(field, 'verbose_name') else field.name.replace('_', ' ').title(),
                        'help_text': field.help_text if hasattr(field, 'help_text') else '',
                    })
        else:
            # For other models, use a more generic approach
            for field in model._meta.get_fields():
                # Skip many-to-many and reverse relations
                if field.is_relation and (field.many_to_many or field.one_to_many):
                    continue
                
                # Skip fields you never want to include
                if field.name in ['password', 'last_login', 'sensitive_data']:
                    continue
                    
                # Include direct fields and foreign keys
                primary_fields.append({
                    'name': field.name,
                    'type': 'direct',
                    'verbose_name': field.verbose_name if hasattr(field, 'verbose_name') else field.name.replace('_', ' ').title(),
                    'help_text': field.help_text if hasattr(field, 'help_text') else '',
                })
        
        field_groups.append({
            'name': model._meta.verbose_name.title(),
            'fields': primary_fields
        })
        
        # 2. Add related fields (customize this part based on your data models)
        if data_area == 'job':
            # Manually define related fields for Jobs
            field_groups.append({
                'name': 'Client Information',
                'fields': [
                    {
                        'name': 'client__name',
                        'type': 'related',
                        'verbose_name': 'Client Name',
                        'help_text': 'Name of the client'
                    },
                    {
                        'name': 'client__industry',
                        'type': 'related',
                        'verbose_name': 'Client Industry',
                        'help_text': 'Industry of the client'
                    }
                ]
            })
            
            field_groups.append({
                'name': 'Organisational Unit',
                'fields': [
                    {
                        'name': 'unit__name',
                        'type': 'related',
                        'verbose_name': 'Unit Name',
                        'help_text': 'Name of the unit'
                    }
                ]
            })
        elif data_area == 'user':
            # Manually define related fields for Users
            field_groups.append({
                'name': 'Manager Information',
                'fields': [
                    {
                        'name': 'manager__first_name',
                        'type': 'related',
                        'verbose_name': 'Manager First Name',
                        'help_text': ''
                    },
                    {
                        'name': 'manager__last_name',
                        'type': 'related',
                        'verbose_name': 'Manager Last Name',
                        'help_text': ''
                    }
                ]
            })
        else:
            # Generic approach for other models
            for field in model._meta.get_fields():
                if field.is_relation and field.related_model:
                    related_model = field.related_model
                    related_fields = []
                    
                    # For each related model, define which fields to include
                    for related_field in related_model._meta.get_fields():
                        # Skip many-to-many and reverse relations
                        if related_field.is_relation and (related_field.many_to_many or related_field.one_to_many):
                            continue
                        
                        # Skip sensitive fields
                        if related_field.name in ['password', 'sensitive_data']:
                            continue
                            
                        # Include direct fields only
                        if not related_field.is_relation or related_field.many_to_one:
                            related_fields.append({
                                'name': f"{field.name}__{related_field.name}",
                                'type': 'related',
                                'verbose_name': f"{field.name} {related_field.name}".replace('_', ' ').title(),
                                'help_text': related_field.help_text if hasattr(related_field, 'help_text') else '',
                            })
                    
                    if related_fields:
                        field_groups.append({
                            'name': related_model._meta.verbose_name.title(),
                            'fields': related_fields
                        })
        
        # 3. Add calculated/aggregated fields
        calculated_fields = []
        
        # Define calculated fields specific to each data area
        if data_area == 'user':
            calculated_fields.extend([
                {
                    'name': 'full_name',
                    'type': 'concat',
                    'verbose_name': 'Full Name',
                    'help_text': 'First name and last name combined',
                    'source_fields': ['first_name', 'last_name'],
                    'separator': ' '
                },
                {
                    'name': 'job_count',
                    'type': 'aggregation',
                    'verbose_name': 'Job Count',
                    'help_text': 'Count of jobs associated with the user',
                    'aggregation': 'count',
                    'related_field': 'jobs_created'
                }
            ])
        elif data_area == 'job':
            calculated_fields.extend([
                {
                    'name': 'phase_count',
                    'type': 'aggregation',
                    'verbose_name': 'Phase Count',
                    'help_text': 'Count of phases in the job',
                    'aggregation': 'count',
                    'related_field': 'phases'
                },
                {
                    'name': 'total_hours',
                    'type': 'aggregation',
                    'verbose_name': 'Total Hours',
                    'help_text': 'Sum of all hours across all phases',
                    'aggregation': 'sum',
                    'related_field': 'phases__timeslots__hours'
                }
            ])
        
        if calculated_fields:
            field_groups.append({
                'name': 'Calculated Fields',
                'fields': calculated_fields
            })
            
        return field_groups
        
    def clean(self):
        cleaned_data = super().clean()
        # The selected fields come from POST data, not form fields
        selected_fields = self.data.getlist('selected_fields', [])
        
        if not selected_fields:
            raise forms.ValidationError(_('You must select at least one field for your report.'))
            
        # Store selected fields in the form's cleaned data
        cleaned_data['selected_fields'] = selected_fields
        return cleaned_data


class DefineFilterForm(ReportDesignerBaseForm):
    """Form for defining filter conditions"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # This form doesn't have regular fields - it uses a dynamic
        # filter builder interface
        
        self.helper.layout = Layout(
            HTML('<h3>Step 4: Define Filters</h3>'),
            HTML('<p>Create filters to limit which records appear in the report.</p>'),
            HTML('<div id="filter-builder" data-fields=\'{{ available_fields_json }}\'></div>'),
            ButtonHolder(
                HTML('<a href="{% url "reporting:report_wizard_step3" %}" class="btn btn-default">Back</a>'),
                Submit('next', _('Next Step'), css_class='btn-primary')
            )
        )


class DefineSortOrderForm(ReportDesignerBaseForm):
    """Form for defining the sort order"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # This form uses a custom interface for arranging the sort order
        
        self.helper.layout = Layout(
            HTML('<h3>Step 5: Define Sort Order</h3>'),
            HTML('<p>Specify how records should be sorted in the report.</p>'),
            HTML('<div id="sort-order-builder" data-fields=\'{{ selected_fields_json }}\'></div>'),
            ButtonHolder(
                HTML('<a href="{% url "reporting:report_wizard_step4" %}" class="btn btn-default">Back</a>'),
                Submit('next', _('Next Step'), css_class='btn-primary')
            )
        )