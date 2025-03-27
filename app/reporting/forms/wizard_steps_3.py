from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.layout import Layout, Submit, Div, Field, HTML, ButtonHolder

from .base import ReportDesignerBaseForm
from ..models import ReportCategory


class SelectPresentationForm(ReportDesignerBaseForm):
    """Form for selecting report presentation options"""
    
    presentation_type = forms.ChoiceField(
        label=_('Presentation Type'),
        choices=[
            ('excel', _('Excel Spreadsheet')),
            ('html', _('Web Page (HTML)')),
            ('pdf', _('PDF Document')),
            ('word', _('Word Document')),
            ('csv', _('CSV File')),
            ('text', _('Text File')),
            ('analysis', _('Analysis Report')),
        ],
        required=True,
        initial='excel',
        widget=forms.RadioSelect
    )
    
    allow_choice_at_runtime = forms.BooleanField(
        label=_('Allow output format choice at runtime'),
        required=False,
        initial=True
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial values if available
        if 'presentation_type' in self.report_data:
            self.fields['presentation_type'].initial = self.report_data['presentation_type']
            
        if 'allow_choice_at_runtime' in self.report_data:
            self.fields['allow_choice_at_runtime'].initial = self.report_data['allow_choice_at_runtime']
            
        # Layout for the form
        self.helper.layout = Layout(
            HTML('<h3>Step 6: Select Presentation</h3>'),
            HTML('<p>Choose how your report should be presented and formatted.</p>'),
            Field('presentation_type', template='reporting/widgets/presentation_selector.html'),
            Field('allow_choice_at_runtime'),
            
            # Excel-specific options
            Div(
                HTML('<h4>Excel Options</h4>'),
                Field('excel_template'),
                css_class='presentation-options',
                data_presentation='excel'
            ),
            
            # Other presentation-specific options would go here
            
            ButtonHolder(
                HTML('<a href="{% url "reporting:report_wizard_step5" %}" class="btn btn-default">Back</a>'),
                Submit('next', _('Next Step'), css_class='btn-primary')
            )
        )
        
        # Add format-specific fields
        self.fields['excel_template'] = forms.ChoiceField(
            label=_('Excel Template'),
            choices=[
                ('standard', _('Standard Template')),
                ('custom', _('Custom Template')),
            ],
            required=False
        )
        # More format-specific fields could be added here


class SaveReportForm(ReportDesignerBaseForm):
    """Form for saving the report definition"""
    
    name = forms.CharField(
        label=_('Report Name'),
        max_length=255,
        required=True
    )
    
    description = forms.CharField(
        label=_('Description'),
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False
    )
    
    category = forms.ModelChoiceField(
        label=_('Category'),
        queryset=ReportCategory.objects.all(),
        required=False
    )
    
    is_private = forms.BooleanField(
        label=_('Private Report'),
        help_text=_('If checked, only you can see this report'),
        required=False,
        initial=True
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial values if available
        if 'name' in self.report_data:
            self.fields['name'].initial = self.report_data['name']
            
        if 'description' in self.report_data:
            self.fields['description'].initial = self.report_data['description']
            
        if 'category' in self.report_data:
            self.fields['category'].initial = self.report_data['category']
            
        if 'is_private' in self.report_data:
            self.fields['is_private'].initial = self.report_data['is_private']
            
        # Layout for the form
        self.helper.layout = Layout(
            HTML('<h3>Step 7: Save Report</h3>'),
            HTML('<p>Provide a name and description for your report.</p>'),
            Field('name'),
            Field('description'),
            Field('category'),
            Field('is_private'),
            ButtonHolder(
                HTML('<a href="{% url "reporting:report_wizard_step6" %}" class="btn btn-default">Back</a>'),
                Submit('save', _('Save Report'), css_class='btn-success')
            )
        )