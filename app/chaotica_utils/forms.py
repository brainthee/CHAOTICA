from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from django import forms
from .models import LeaveRequest, User, Group, UserInvitation
from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import FormActions,PrependedText, FieldWithButtons, StrictButton, InlineField, Accordion, AccordionGroup
from crispy_forms.layout import Layout, Row, Column, Field, Div, Submit, Button, HTML
from crispy_bootstrap5.bootstrap5 import FloatingField
from constance.forms import ConstanceForm
from dal import autocomplete
import pytz
from django.conf import settings
from bootstrap_datepicker_plus.widgets import TimePickerInput, DatePickerInput, DateTimePickerInput
from django.core.files.images import get_image_dimensions
from business_duration import businessDuration


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
        self.request = kwargs.pop('request', None)
        super(LeaveRequestForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['start_date'].label = False
        self.fields['end_date'].label = False
        self.fields['type_of_leave'].label = False
        self.fields['notes'].label = False
        self.fields['start_date'].widget = DateTimePickerInput()
        self.fields['end_date'].widget = DateTimePickerInput()


    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        today = timezone.now()

        if LeaveRequest.objects.filter(user=self.request.user, cancelled=False,
            start_date__lte=end,
            end_date__gte=start).exists():
            self.add_error(None, "Unable to save. The dates overlap an existing leave request.")

        if start < today:
            self.add_error('start_date', "The start date is before today.")

        if start > end:
            self.add_error('end_date', "The end date is before the start date.")

        # Now lets check if this takes us over our available leave
        unit='day'
        days = businessDuration(start, end, unit=unit)
        requested_days = round(days, 2)
        available_days = self.request.user.remaining_leave()
        if requested_days > available_days:
            self.add_error(None, "You have requested more days than your allocation ({} required, {} available)".format(str(requested_days), str(available_days)))

    class Meta:
        model = LeaveRequest
        fields = ('start_date', 'end_date', 'type_of_leave', 'notes',)

class InviteUserForm(forms.ModelForm):
    invited_email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super(InviteUserForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Div(FloatingField('invited_email'),
                        css_class="input-group input-group-dynamic"),
            ),
            Div(StrictButton("Invite User", type="submit", 
                    css_class="btn btn-primary w-100 mb-3"),
                css_class="button-row d-flex mt-4"),
        )

    class Meta:
        model = UserInvitation
        fields = ('invited_email',)


class ChaoticaUserForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        self.invite = kwargs.pop('invite', None)
        super(ChaoticaUserForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if self.invite:
            self.fields['email'].initial = self.invite.invited_email
            self.fields['email'].disabled = True
        self.helper.layout = Layout(
            Row(
                Column(Div(FloatingField('first_name'),
                        css_class="input-group input-group-dynamic")),
                Column(Div(FloatingField('last_name'),
                        css_class="input-group input-group-dynamic")),
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
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2' )
        widgets = {
            'first_name': forms.TextInput(attrs={'autofocus': True}),
        }

class AssignRoleForm(forms.ModelForm):
    
    def __init__(self, *args, **kwargs):
        super(AssignRoleForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields['groups'].queryset = Group.objects.filter(name__startswith=settings.GLOBAL_GROUP_PREFIX)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("groups", style="width: 100%;"),
        )

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
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2' )

class ProfileBasicForm(forms.ModelForm):

    profile_image = forms.FileField(
        label="Profile Image",
    )
    pref_timezone = forms.ChoiceField(
        choices=[(x, x) for x in pytz.common_timezones],
        widget=autocomplete.ModelSelect2())

    def __init__(self, *args, **kwargs):
        super(ProfileBasicForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.fields['contracted_leave_renewal'].widget = DatePickerInput()
        self.fields['show_help'].help_text = False
        
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
                Column(Div(FloatingField('job_title'),
                        css_class="input-group input-group-dynamic")),
            ),
            Row(
                Column(Div(Field('profile_image'),
                        css_class="input-group input-group-dynamic")),
                Column(
                    Row(
                        Column(Div(Field('contracted_leave'),
                                css_class="input-group input-group-dynamic")),
                        Column(Div(Field('contracted_leave_renewal'),
                                css_class="input-group input-group-dynamic")),
                    ),
                ),
            ),
            Row(
                Column(Div(Field('languages'),
                        css_class="")),
                Column(Div(Field('pref_timezone'),
                        css_class="")),
            ),
        )

    class Meta:
        model = User
        widgets = {
            'languages': autocomplete.ModelSelect2Multiple(),
        }
        fields = ('first_name', 'last_name', 'profile_image', 'pref_timezone', 'email', 'phone_number', 'job_title', 'show_help', 'location', 'languages','contracted_leave', 'contracted_leave_renewal')


    def clean_profile_image(self):
        profile_image = self.cleaned_data['profile_image']

        try:
            w, h = get_image_dimensions(profile_image)

            #validate dimensions
            max_width = max_height = 500
            if (w and h) and (w > max_width or h > max_height):
                self.add_error("profile_image",
                    'Please use an image that is '
                    '%s x %s pixels or smaller.' % (max_width, max_height))

            #validate content type
            main, sub = profile_image.content_type.split('/')
            if not (main == 'image' and sub in ['jpeg', 'pjpeg', 'gif', 'png']):
               self.add_error("profile_image",'Please use a JPEG, '
                    'GIF or PNG image.')

            #validate file size
            if len(profile_image) > (1024 * 1024):
                self.add_error("profile_image",
                    'Avatar file size may not exceed 1M.')

        except AttributeError:
            """
            Handles case when we are updating the user profile
            and do not supply a new avatar
            """
            pass

        return profile_image

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