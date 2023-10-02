from django.contrib.auth.forms import UserCreationForm
from django import forms
from .models import *
from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import FormActions,PrependedText, FieldWithButtons, StrictButton, InlineField, Accordion, AccordionGroup
from crispy_forms.layout import Layout, Row, Column, Field, Div, Submit, Button, HTML
from crispy_bootstrap5.bootstrap5 import FloatingField
from constance.forms import ConstanceForm
from dal import autocomplete
from django.conf import settings
from bootstrap_datepicker_plus.widgets import TimePickerInput, DatePickerInput, DateTimePickerInput


class CustomConfigForm(ConstanceForm):
      
      def __init__(self, *args, **kwargs):
        super(CustomConfigForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(Div(Field('SITE_NOTICE_ENABLED'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('SITE_NOTICE_COLOUR'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('SITE_NOTICE_MSG'),
                        css_class="input-group input-group-dynamic")),
            ),
        )


class LeaveRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(LeaveRequestForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['start_date'].widget = DatePickerInput()
        self.fields['end_date'].widget = DatePickerInput()
        self.helper.layout = Layout(
            Row(
                Column(Div(FloatingField('start_date'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('end_date'),
                        css_class="input-group input-group-dynamic")),
            ),
            Row(
                Div(FloatingField('type_of_leave'),
                        css_class="input-group input-group-dynamic"),
            ),
            Row(
                Div(FloatingField('notes'),
                        css_class="input-group input-group-dynamic"),
            ),
        )
    
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")

        if start > end:
            raise ValidationError(
                "The end date must occur after the start date."
            )

    class Meta:
        model = LeaveRequest
        fields = ('start_date', 'end_date', 'type_of_leave', 'notes',)

class ChaoticaUserForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super(ChaoticaUserForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['username'].widget.attrs.pop("autofocus", None)
        self.helper.layout = Layout(
            Row(
                Column(Div(FloatingField('first_name'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('last_name'),
                        css_class="input-group input-group-dynamic")),
            ),
            Row(
                Div(FloatingField('username'),
                        css_class="input-group input-group-dynamic"),
            ),
            Row(
                Div(FloatingField('email'),
                        css_class="input-group input-group-dynamic"),
            ),
            Row(
                Column(Div(FloatingField('password1'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('password2'),
                        css_class="input-group input-group-dynamic")),
            ),
            Div(StrictButton("Create User", type="submit", 
                    css_class="btn btn-primary w-100 mb-3"),
                css_class="button-row d-flex mt-4"),
        )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2' )
        help_texts = {
            'username': None,
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'autofocus': True}),
        }

class AssignRoleForm(forms.ModelForm):
    
    def __init__(self, *args, **kwargs):
        super(AssignRoleForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['groups'].queryset = Group.objects.filter(name__startswith=settings.GLOBAL_GROUP_PREFIX)
        self.helper.form_tag = False

    class Meta:
        model = User
        widgets = {
            'groups': autocomplete.ModelSelect2Multiple(),
        }
        fields = ('groups',)


class ProfileForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2' )
        help_texts = {
            'username': None,
        }

class ProfileBasicForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(ProfileBasicForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        
        self.helper.layout = Layout(
            Row(
                Column(Div(FloatingField('first_name'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('last_name'),
                        css_class="input-group input-group-dynamic")),
            ),
            Row(
                Column(Div(FloatingField('email'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('location'),
                        css_class="input-group input-group-dynamic")),
            ),
            Row(
                Column(Div(FloatingField('phone_number'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(Field('languages'),
                        css_class="input-group input-group-dynamic")),
            ),
            Row(
                Column(Div(FloatingField('job_title'),
                        css_class="input-group input-group-dynamic")),
            ),
        )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone_number', 'job_title', 'show_help', 'location', 'languages')

class ImportSiteDataForm(forms.Form):
    importFile = forms.FileField(required=False, label='JSON Data')
    def __init__(self, *args, **kwargs):
        super(ImportSiteDataForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Div(
                Row(
                    Div(Field('importFile'),
                        css_class="input-group input-group-dynamic")
                ),
                css_class='modal-body pt-3'),

            Div(
                Div(StrictButton("Import", type="submit", 
                    css_class="btn bg-gradient-success ms-auto mb-0"),
                css_class="button-row d-flex mt-4"),
            css_class="modal-footer"),
        )

    class Meta:
        fields = ('importFile')