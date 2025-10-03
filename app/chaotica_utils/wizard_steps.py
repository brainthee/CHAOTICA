# Wizard forms for initial setup
from django import forms
from django.contrib.auth.forms import UserCreationForm
from chaotica_utils.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column, Div
from crispy_forms.bootstrap import StrictButton
from crispy_bootstrap5.bootstrap5 import FloatingField

class WizardUserForm(UserCreationForm):
    """Simplified user creation form for the setup wizard"""
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(
                    FloatingField("first_name"),
                    css_class="col-md-6"
                ),
                Column(
                    FloatingField("last_name"),
                    css_class="col-md-6"
                ),
            ),
            FloatingField("email"),
            Row(
                Column(
                    FloatingField("password1"),
                    css_class="col-md-6"
                ),
                Column(
                    FloatingField("password2"),
                    css_class="col-md-6"
                ),
            ),
        )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "password1", "password2")


class WizardOrganisationForm(forms.Form):
    """Simplified organisation unit form for the setup wizard"""
    name = forms.CharField(max_length=255, required=True)
    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False
    )
    lead = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            FloatingField("name"),
            FloatingField("description"),
        )

        # Set the lead to the created admin user
        if self.user:
            self.fields['lead'].initial = self.user.pk if self.user else None


class WizardServiceForm(forms.Form):
    """Form for creating multiple services at once"""
    services = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        help_text="Enter one service per line (e.g., Web Application Testing, Network Assessment, Red Team)",
        label="Services to Create"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_services(self):
        services_text = self.cleaned_data['services']
        services = [s.strip() for s in services_text.splitlines() if s.strip()]
        if not services:
            raise forms.ValidationError("Please enter at least one service")
        return services


class WizardSkillForm(forms.Form):
    """Form for creating skill categories and skills"""
    categories = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text="Enter skill categories, one per line (e.g., Technical, Soft Skills, Certifications)",
        label="Skill Categories"
    )

    skills = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 8}),
        help_text="Enter skills with their category, format: 'Category: Skill Name' (e.g., 'Technical: Python Programming')",
        label="Skills",
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_categories(self):
        categories_text = self.cleaned_data['categories']
        categories = [c.strip() for c in categories_text.splitlines() if c.strip()]
        if not categories:
            raise forms.ValidationError("Please enter at least one category")
        return categories

    def clean_skills(self):
        skills_text = self.cleaned_data.get('skills', '')
        skills = []
        for line in skills_text.splitlines():
            line = line.strip()
            if line and ':' in line:
                category, skill = line.split(':', 1)
                skills.append({
                    'category': category.strip(),
                    'name': skill.strip()
                })
        return skills


class WizardClientForm(forms.Form):
    """Form for creating multiple clients at once"""
    clients = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6}),
        help_text="Enter client names, one per line",
        label="Initial Clients"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_clients(self):
        clients_text = self.cleaned_data['clients']
        clients = [c.strip() for c in clients_text.splitlines() if c.strip()]
        if not clients:
            raise forms.ValidationError("Please enter at least one client")
        return clients