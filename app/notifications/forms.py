from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

from .models import (
    NotificationSubscription,
    SubscriptionRule,
    GlobalRoleCriteria,
    OrgUnitRoleCriteria,
    JobRoleCriteria,
    PhaseRoleCriteria,
    DynamicRuleCriteria
)
from .enums import NotificationTypes
from jobtracker.models import OrganisationalUnitRole
from chaotica_utils.enums import GlobalRoles

class SubscriptionRuleForm(forms.ModelForm):
    """Form for creating and editing subscription rules"""
    class Meta:
        model = SubscriptionRule
        fields = ['name', 'description', 'notification_type', 'priority', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'priority': forms.NumberInput(attrs={'min': 0, 'max': 100}),
        }
        help_texts = {
            'name': _('A descriptive name for this subscription rule.'),
            'description': _('Optional description explaining what this rule does.'),
            'notification_type': _('The type of notification this rule applies to.'),
            'priority': _('Higher numbers mean higher priority. Rules with the same priority are all applied.'),
            'is_active': _('Inactive rules are not applied.'),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notification_type'].choices = NotificationTypes.CHOICES
        self.fields['priority'].validators = [MinValueValidator(0)]

class GlobalRoleCriteriaForm(forms.ModelForm):
    """Form for adding global role criteria"""
    class Meta:
        model = GlobalRoleCriteria
        fields = ['role']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = GlobalRoles.CHOICES
        self.fields['role'].label = 'Global Role'
        self.fields['role'].help_text = 'Users with this global role will be subscribed.'

class OrgUnitRoleCriteriaForm(forms.ModelForm):
    """Form for adding org unit role criteria"""
    class Meta:
        model = OrgUnitRoleCriteria
        fields = ['unit_role']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_role'].queryset = OrganisationalUnitRole.objects.all()
        self.fields['unit_role'].label = 'Unit Role'
        self.fields['unit_role'].help_text = 'Users with this role in the relevant organizational unit will be subscribed.'

class JobRoleCriteriaForm(forms.ModelForm):
    """Form for adding job role criteria"""
    class Meta:
        model = JobRoleCriteria
        fields = ['role_id']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class PhaseRoleCriteriaForm(forms.ModelForm):
    """Form for adding job role criteria"""
    class Meta:
        model = PhaseRoleCriteria
        fields = ['role_id']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class DynamicRuleCriteriaForm(forms.ModelForm):
    """Form for adding dynamic criteria"""
    class Meta:
        model = DynamicRuleCriteria
        fields = ['criteria_name', 'parameters']
        widgets = {
            'parameters': forms.Textarea(attrs={'rows': 3, 'placeholder': '{"param1": "value1", "param2": "value2"}'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The choices will be set in the view
        self.fields['criteria_name'] = forms.ChoiceField(
            choices=[],
            label='Criteria Function',
            help_text='The dynamic criteria function to use.'
        )
        self.fields['parameters'].label = 'Parameters (JSON)'
        self.fields['parameters'].help_text = 'Optional parameters for the criteria function in JSON format.'