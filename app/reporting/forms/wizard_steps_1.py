from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.layout import Layout, Submit, Div, Field, HTML, ButtonHolder

from .base import ReportDesignerBaseForm
from jobtracker.models import OrganisationalUnit, Client

class SelectDataAreaForm(ReportDesignerBaseForm):
    """Form for selecting the data area (report focus)"""
    DATA_AREAS = (
        ('user', _('People (Users)')),
        ('job', _('Jobs')),
        ('phase', _('Phases')),
        ('timeslot', _('Schedule')),
        ('project', _('Projects')),
        ('client', _('Clients')),
        ('team', _('Teams')),
        ('skill', _('Skills')),
        ('organisational_unit', _('Organisational Units')),
        ('leave_request', _('Leave Requests')),
    )
    
    data_area = forms.ChoiceField(
        label=_('Data Area (Report Focus)'),
        choices=DATA_AREAS,
        required=True,
        widget=forms.RadioSelect,
        help_text=_('Select the primary focus of your report')
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial value if available from report_data
        if 'data_area' in self.report_data:
            self.fields['data_area'].initial = self.report_data['data_area']
            
        # Custom layout for better presentation
        self.helper.layout = Layout(
            HTML('<h3>Step 1: Select Data Area</h3>'),
            HTML('<p>This is the primary focus of your report. It determines the main data your report will be based on.</p>'),
            Field('data_area', template='reporting/widgets/data_area_selector.html'),
            ButtonHolder(
                Submit('next', _('Next Step'), css_class='btn-primary')
            )
        )


class RefineDataAreaForm(ReportDesignerBaseForm):
    """Form for refining the data area population"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Debug log
        import logging
        logger = logging.getLogger(__name__)
        
        # The available fields depend on the selected data area
        data_area = self.report_data.get('data_area')
        from pprint import pprint
        pprint (self.report_data)
        logger.info(f"Refining data area: {data_area}")
        
        if data_area == 'user':
            logger.info("Adding User population fields")
            self.fields['population_type'] = forms.ChoiceField(
                label=_('User Population'),
                choices=[
                    ('all', _('All Users')),
                    ('active_only', _('Active Users Only')),
                    ('with_manager', _('Users with Manager')),
                    ('within_orgunit', _('Users within Organisational Unit')),
                ],
                initial=self.report_data.get('population_type', 'active_only'),
                required=True,
                widget=forms.RadioSelect
            )
            
            # Conditional field - only shown for 'within_orgunit'
            self.fields['organisational_unit'] = forms.ModelChoiceField(
                label=_('Select Organisational Unit'),
                queryset=OrganisationalUnit.objects.all(),
                required=False,
                help_text=_('Only required if "Users within Organisational Unit" is selected')
            )
            
        elif data_area == 'job':
            logger.info("Adding Job population fields")
            self.fields['population_type'] = forms.ChoiceField(
                label=_('Job Population'),
                choices=[
                    ('all', _('All Jobs')),
                    ('active_only', _('Active Jobs Only')),
                    ('current_year', _('Current Year')),
                    ('by_client', _('Jobs for Specific Client')),
                    ('by_unit', _('Jobs for Specific Organisational Unit')),
                ],
                initial=self.report_data.get('population_type', 'active_only'),
                required=True,
                widget=forms.RadioSelect
            )
            
            # Conditional fields
            self.fields['client'] = forms.ModelChoiceField(
                label=_('Select Client'),
                queryset=Client.objects.all(),
                required=False,
                help_text=_('Only required if "Jobs for Specific Client" is selected')
            )
            
            self.fields['unit'] = forms.ModelChoiceField(
                label=_('Select Organisational Unit'),
                queryset=OrganisationalUnit.objects.all(),
                required=False,
                help_text=_('Only required if "Jobs for Specific Organisational Unit" is selected')
            )
        elif data_area == 'phase':
            logger.info("Adding Phase population fields")
            self.fields['population_type'] = forms.ChoiceField(
                label=_('Phase Population'),
                choices=[
                    ('all', _('All Phases')),
                    ('active_only', _('Active Phases Only')),
                    ('completed', _('Completed Phases')),
                    ('by_service', _('Phases for Specific Service')),
                ],
                initial=self.report_data.get('population_type', 'active_only'),
                required=True,
                widget=forms.RadioSelect
            )
        elif data_area == 'timeslot':
            logger.info("Adding TimeSlot population fields")
            self.fields['population_type'] = forms.ChoiceField(
                label=_('Schedule Population'),
                choices=[
                    ('all', _('All Schedule Entries')),
                    ('future_only', _('Future Entries Only')),
                    ('past_only', _('Past Entries Only')),
                    ('date_range', _('Specific Date Range')),
                ],
                initial=self.report_data.get('population_type', 'future_only'),
                required=True,
                widget=forms.RadioSelect
            )
            
            # Date range fields
            self.fields['start_date'] = forms.DateField(
                label=_('Start Date'),
                required=False,
                widget=forms.DateInput(attrs={'type': 'date'}),
                help_text=_('Only required if "Specific Date Range" is selected')
            )
            
            self.fields['end_date'] = forms.DateField(
                label=_('End Date'),
                required=False,
                widget=forms.DateInput(attrs={'type': 'date'}),
                help_text=_('Only required if "Specific Date Range" is selected')
            )
        else:
            logger.warning(f"No population fields defined for data area: {data_area}")
            # Add a default field for data areas without specific refinement options
            print(data_area)
            self.fields['population_type'] = forms.ChoiceField(
                label=_('Population'),
                choices=[
                    ('all', _('All Records')),
                ],
                initial='all',
                required=True,
                widget=forms.RadioSelect
            )
            
        # Custom layout for better presentation
        self.helper.layout = Layout(
            HTML('<h3>Step 2: Refine Data Area</h3>'),
            HTML('<p>Narrow down the population of records your report will include.</p>'),
            Field('population_type'),
        )
        
    def clean(self):
        cleaned_data = super().clean()
        population_type = cleaned_data.get('population_type')
        
        # Validate conditional required fields
        if self.report_data.get('data_area') == 'user':
            if population_type == 'within_orgunit' and not cleaned_data.get('organisational_unit'):
                self.add_error('organisational_unit', _('This field is required when selecting "Users within Organisational Unit"'))
                
        elif self.report_data.get('data_area') == 'job':
            if population_type == 'by_client' and not cleaned_data.get('client'):
                self.add_error('client', _('This field is required when selecting "Jobs for Specific Client"'))
            elif population_type == 'by_unit' and not cleaned_data.get('unit'):
                self.add_error('unit', _('This field is required when selecting "Jobs for Specific Organisational Unit"'))
                
        return cleaned_data