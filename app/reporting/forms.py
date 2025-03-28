from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    Report, ReportCategory, ReportField, ReportFilter, ReportSort,
    DataArea, DataField, FilterType
)

class SelectDataAreaForm(forms.Form):
    """Form for selecting the data area (first step of report wizard)"""
    data_area = forms.ModelChoiceField(
        queryset=DataArea.objects.filter(is_available=True),
        empty_label=None,
        label=_("Data Area"),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=_("Select the main focus of your report")
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter data areas by user permissions if needed
        if user and not user.is_superuser:
            # This is where you implement permission filtering
            # For now, we'll use all available data areas
            pass


class SelectFieldsForm(forms.Form):
    """Form for selecting report fields"""
    
    def __init__(self, *args, **kwargs):
        data_area = kwargs.pop('data_area', None)
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if data_area:
            # Get all fields for the data area
            fields = DataField.objects.filter(
                data_area=data_area,
                is_available=True
            ).order_by('group', 'display_name')
            
            # Filter sensitive fields based on user permissions
            if user and not user.is_superuser:
                restricted_fields = []
                for field in fields:
                    if field.is_sensitive and field.requires_permission:
                        if not user.has_perm(field.requires_permission):
                            restricted_fields.append(field.id)
                
                if restricted_fields:
                    fields = fields.exclude(id__in=restricted_fields)
            
            # Group fields by their group property
            field_groups = {}
            for field in fields:
                group_name = field.group or 'General'
                if group_name not in field_groups:
                    field_groups[group_name] = []
                field_groups[group_name].append(field)
            
            # Add a multiple choice field for each group
            for group_name, group_fields in field_groups.items():
                field_name = f'group_{group_name}'
                
                self.fields[field_name] = forms.ModelMultipleChoiceField(
                    queryset=DataField.objects.filter(id__in=[f.id for f in group_fields]),
                    label=group_name,
                    required=False,
                    widget=forms.CheckboxSelectMultiple(attrs={'class': 'list-unstyled'}),
                )
                
                # Debug: Check if this field has initial values
                if self.initial and field_name in self.initial:
                    # Try to ensure the initial value is properly set
                    initial_ids = self.initial[field_name]
                    self.fields[field_name].initial = initial_ids
            

    def get_selected_fields(self):
        """Get all selected fields from all groups"""
        selected_fields = []
        for field_name, value in self.cleaned_data.items():
            if field_name.startswith('group_') and value:
                selected_fields.extend(value)
        return selected_fields


class FilterConditionForm(forms.Form):
    """Form for a single filter condition"""
    data_field = forms.ModelChoiceField(
        queryset=DataField.objects.filter(is_available=True),
        label=_("Field"),
        widget=forms.Select(attrs={'class': 'form-select filter-field'})
    )
    
    filter_type = forms.ModelChoiceField(
        queryset=FilterType.objects.filter(is_available=True),
        label=_("Condition"),
        widget=forms.Select(attrs={'class': 'form-select filter-type'})
    )
    
    value = forms.CharField(
        required=False,
        label=_("Value"),
        widget=forms.TextInput(attrs={'class': 'form-control filter-value'})
    )
    
    prompt_at_runtime = forms.BooleanField(
        required=False,
        label=_("Prompt at runtime"),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    prompt_text = forms.CharField(
        required=False,
        label=_("Prompt text"),
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    operator = forms.ChoiceField(
        choices=[('and', 'AND'), ('or', 'OR')],
        initial='and',
        label=_("Operator"),
        widget=forms.Select(attrs={'class': 'form-select filter-operator'})
    )
    
    def __init__(self, *args, **kwargs):
        data_area = kwargs.pop('data_area', None)
        super().__init__(*args, **kwargs)
        
        if data_area:
            # Limit fields to the selected data area
            self.fields['data_field'].queryset = DataField.objects.filter(
                data_area=data_area,
                is_available=True
            ).order_by('group', 'display_name')


class DefineFiltersForm(forms.Form):
    """Form for defining filter conditions"""
    
    def __init__(self, *args, **kwargs):
        data_area = kwargs.pop('data_area', None)
        super().__init__(*args, **kwargs)
        
        # Add a hidden field to store JSON representation of all filters
        self.fields['filter_conditions'] = forms.CharField(
            widget=forms.HiddenInput(),
            required=False
        )



class DefineSortOrderForm(forms.Form):
    """Form for defining sort order"""
    
    def __init__(self, *args, **kwargs):
        data_area = kwargs.pop('data_area', None)
        fields = kwargs.pop('fields', [])
        super().__init__(*args, **kwargs)
        
        # Create a hidden field to store selected sort fields
        self.fields['sort_fields'] = forms.CharField(
            widget=forms.HiddenInput(),
            required=False
        )
        
        # Create fields for each selected report field
        if fields:
            for i, field in enumerate(fields):
                # Field to include in sort
                self.fields[f'sort_field_{field.id}'] = forms.BooleanField(
                    label=field.display_name,
                    required=False,
                    widget=forms.CheckboxInput(attrs={'class': 'form-check-input sort-field-checkbox'})
                )
                
                # Sort direction
                self.fields[f'sort_direction_{field.id}'] = forms.ChoiceField(
                    choices=[('asc', 'Ascending'), ('desc', 'Descending')],
                    initial='asc',
                    required=False,
                    widget=forms.Select(attrs={'class': 'form-select sort-direction'})
                )
                
                # Sort position (used for drag-and-drop reordering)
                self.fields[f'sort_position_{field.id}'] = forms.IntegerField(
                    initial=i,
                    required=False,  # Make this field optional
                    widget=forms.HiddenInput(attrs={'class': 'sort-position'})
                )
    
    def clean(self):
        """Custom validation to handle position fields only for checked fields"""
        cleaned_data = super().clean()
        
        # Only validate positions for selected fields
        for field_name, value in self.cleaned_data.items():
            if field_name.startswith('sort_field_') and value:
                # This field is checked for sorting
                field_id = field_name.replace('sort_field_', '')
                position_field = f'sort_position_{field_id}'
                
                # Ensure the position field has a value
                if position_field in self.cleaned_data and self.cleaned_data[position_field] is None:
                    # Default to 0 if not provided
                    self.cleaned_data[position_field] = 0
        
        return cleaned_data



class DefinePresentationForm(forms.Form):
    """Form for defining report presentation"""
    presentation_type = forms.ChoiceField(
        choices=Report.PRESENTATION_CHOICES,
        initial='excel',
        label=_("Output Format"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    allow_presentation_choice = forms.BooleanField(
        required=False,
        initial=False,
        label=_("Allow users to choose output format at runtime"),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    # Fields for Excel options
    excel_group_records = forms.IntegerField(
        required=False,
        initial=0,
        min_value=0,
        label=_("Group records (rows per group)"),
        help_text=_("Number of rows to group with separating line (0 for no grouping)"),
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    excel_freeze_columns = forms.IntegerField(
        required=False,
        initial=0,
        min_value=0,
        label=_("Freeze columns"),
        help_text=_("Number of columns to freeze when scrolling"),
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    # Fields for PDF options
    pdf_orientation = forms.ChoiceField(
        choices=[('portrait', 'Portrait'), ('landscape', 'Landscape')],
        initial='landscape',
        required=False,
        label=_("Page orientation"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    pdf_paper_size = forms.ChoiceField(
        choices=[('a4', 'A4'), ('letter', 'Letter'), ('legal', 'Legal')],
        initial='a4',
        required=False,
        label=_("Paper size"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Fields for HTML options
    html_include_styling = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Include styling"),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    # Word template options
    word_template = forms.ChoiceField(
        choices=[
            ('standard_portrait', 'Standard Portrait'),
            ('standard_landscape', 'Standard Landscape'),
            ('custom', 'Custom Template')
        ],
        initial='standard_landscape',
        required=False,
        label=_("Template"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Text options
    text_delimiter = forms.ChoiceField(
        choices=[
            ('tab', 'Tab'),
            ('comma', 'Comma'),
            ('semicolon', 'Semicolon'),
            ('pipe', 'Pipe (|)')
        ],
        initial='tab',
        required=False,
        label=_("Field delimiter"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class SaveReportForm(forms.ModelForm):
    """Form for saving the report"""
    class Meta:
        model = Report
        fields = ['name', 'description', 'category', 'is_private']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }