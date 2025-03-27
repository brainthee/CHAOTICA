from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Div, Field, HTML, ButtonHolder

from chaotica_utils.models import User
from ..models import ReportSchedule


class ReportScheduleForm(forms.ModelForm):
    """Form for scheduling reports"""
    
    class Meta:
        model = ReportSchedule
        fields = [
            'name', 'enabled', 'frequency', 'day_of_week', 
            'day_of_month', 'email_subject', 'email_body', 
            'include_as_attachment'
        ]
        widgets = {
            'day_of_week': forms.Select(choices=[
                (0, _('Monday')),
                (1, _('Tuesday')),
                (2, _('Wednesday')),
                (3, _('Thursday')),
                (4, _('Friday')),
                (5, _('Saturday')),
                (6, _('Sunday')),
            ]),
            'day_of_month': forms.Select(choices=[
                (i, str(i)) for i in range(1, 32)
            ]),
            'email_body': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        self.report = kwargs.pop('report', None)
        super().__init__(*args, **kwargs)
        
        self.helper = FormHelper()
        self.helper.form_tag = True
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        
        # Add recipients field (many-to-many)
        self.fields['recipients'] = forms.ModelMultipleChoiceField(
            label=_('Recipients'),
            queryset=User.objects.filter(is_active=True),
            required=True,
            widget=forms.SelectMultiple(attrs={'class': 'select2'})
        )
        
        # Set initial recipients if editing
        if self.instance.pk:
            self.fields['recipients'].initial = self.instance.recipients.all()
        
        # Show/hide fields based on frequency
        self.helper.layout = Layout(
            Field('name'),
            Field('enabled'),
            Field('frequency'),
            Div(
                Field('day_of_week'),
                css_class='conditional-field',
                data_condition='frequency',
                data_condition_value='weekly'
            ),
            Div(
                Field('day_of_month'),
                css_class='conditional-field',
                data_condition='frequency',
                data_condition_value='monthly'
            ),
            Field('recipients'),
            Field('email_subject'),
            Field('email_body'),
            Field('include_as_attachment'),
            ButtonHolder(
                Submit('save', _('Save Schedule'), css_class='btn-success')
            )
        )
    
    def save(self, commit=True):
        schedule = super().save(commit=False)
        
        if self.report:
            schedule.report = self.report
            
        if commit:
            schedule.save()
            
            # Handle many-to-many relationships manually
            self.save_m2m()
            
        return schedule