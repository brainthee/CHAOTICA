from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from django.utils.html import format_html
from django import forms
from .models import LeaveRequest, User, Group, UserInvitation, Holiday
from .enums import LeaveRequestTypes
from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import (
    StrictButton,
)
from crispy_forms.layout import Layout, Row, Column, Field, Div, HTML
from crispy_bootstrap5.bootstrap5 import FloatingField
from django_countries.widgets import CountrySelectWidget
from django_countries.fields import CountryField
from constance.admin import ConstanceForm
from dal import autocomplete
import pytz
from datetime import datetime, timedelta
from django.conf import settings
from constance import config
from bootstrap_datepicker_plus.widgets import (
    DatePickerInput,
    DateTimePickerInput,
)
from django.core.files.images import get_image_dimensions
from business_duration import businessDuration
from django.contrib import messages
from django_clamav.validators import validate_file_infection


class HolidayForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(HolidayForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.fields["date"].widget = DatePickerInput()
        self.fields["date"].label = ""
        self.helper.layout = Layout(
            Row(
                Column(
                    Div(
                        FloatingField("country"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
                Column(
                    Div(
                        FloatingField("date"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
            ),
            Row(
                Div(
                    FloatingField("reason"), css_class="input-group input-group-dynamic"
                ),
            ),
        )

    class Meta:
        model = Holiday
        fields = [
            "date",
            "country",
            "reason",
        ]


class HolidayImportLibForm(forms.Form):
    country = CountryField().formfield()

    def __init__(self, *args, **kwargs):
        super(HolidayImportLibForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Div(
                    FloatingField("country"),
                    css_class="input-group input-group-dynamic",
                ),
            ),
        )

    class Meta:
        fields = [
            "country",
        ]
        widgets = {"country": CountrySelectWidget()}


class CustomConfigForm(ConstanceForm):

    def __init__(self, *args, **kwargs):
        super(CustomConfigForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        for field in self.fields:
            if field in settings.CONSTANCE_CONFIG:
                self.fields[field].help_text = settings.CONSTANCE_CONFIG[field][1]

        self.helper.layout = Layout(
            Row(
                Column(
                    HTML('<h4 class="mb-4">Job/Phase Settings</h4>'),
                    Div(
                        FloatingField("JOB_ID_START"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("PROJECT_ID_START"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("PRECHECK_LATE_HOURS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("TQA_LATE_HOURS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("PQA_LATE_HOURS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("DELIVERY_LATE_HOURS"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
                Column(
                    HTML('<h4 class="mb-4">Work Settings</h4>'),
                    Div(
                        FloatingField("DEFAULT_HOURS_IN_DAY"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("DEFAULT_WORKING_DAYS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("LEAVE_DAYS_NOTICE"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("LEAVE_ENFORCE_LIMIT"),
                        css_class="input-group input-group-dynamic",
                    ),
                    HTML('<h4 class="mb-4">Phase Deadlines</h4>'),
                    Div(
                        FloatingField("DAYS_TO_TQA"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("DAYS_TO_PQA"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("DAYS_TO_DELIVERY"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
            ),
            Row(
                Column(
                    HTML('<h4 class="mb-4">Reminder Settings</h4>'),
                    Div(
                        Field("SKILLS_REVIEW_DAYS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("PROFILE_REVIEW_DAYS"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
                Column(
                    HTML('<h4 class="mb-4">Support Settings</h4>'),
                    Div(
                        Field("SUPPORT_DOC_URL"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SUPPORT_MAILBOX"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SUPPORT_ISSUES"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
                Column(
                    HTML('<h4 class="mb-4">Theme Settings</h4>'),
                    Div(
                        Field("SNOW_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("KONAMI_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
            ),
            Row(
                Column(
                    HTML('<h4 class="mb-4">Auth Settings</h4>'),
                    Div(
                        Field("ADFS_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("ADFS_AUTO_LOGIN"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("LOCAL_LOGIN_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("REGISTRATION_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("INVITE_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("USER_INVITE_EXPIRY"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("EMAIL_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
                Column(
                    HTML('<h4 class="mb-4">Site Notice</h4>'),
                    Div(
                        Field("SITE_NOTICE_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("SITE_NOTICE_COLOUR"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        FloatingField("SITE_NOTICE_MSG"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
            ),
            Row(
                HTML('<h4 class="mb-4">Schedule Colours</h4>'),
                Column(
                    Div(
                        Field("SCHEDULE_COLOR_AVAILABLE"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SCHEDULE_COLOR_UNAVAILABLE"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SCHEDULE_COLOR_INTERNAL"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SCHEDULE_COLOR_PROJECT"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
                Column(
                    Div(
                        Field("SCHEDULE_COLOR_PHASE"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SCHEDULE_COLOR_PHASE_CONFIRMED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SCHEDULE_COLOR_PHASE_AWAY"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("SCHEDULE_COLOR_COMMENT"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
            ),
            Row(
                Column(
                    HTML('<h4 class="mb-4">Resource Manager Settings</h4>'),
                    Div(
                        Field("RM_SYNC_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("RM_SYNC_API_SITE"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("RM_SYNC_API_TOKEN"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("RM_SYNC_STALE_TIMEOUT"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("RM_WARNING_MSG"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
                Column(
                    HTML('<h4 class="mb-4">Additional Notification Recipients</h4>'),
                    Div(
                        Field("NOTIFICATION_POOL_SCOPING_EMAIL_RCPTS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("NOTIFICATION_POOL_SCHEDULING_EMAIL_RCPTS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("NOTIFICATION_POOL_TQA_EMAIL_RCPTS"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("NOTIFICATION_POOL_PQA_EMAIL_RCPTS"),
                        css_class="input-group input-group-dynamic",
                    ),
                ),
            ),
        )


class LeaveRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super(LeaveRequestForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["start_date"].label = False
        self.fields["end_date"].label = False

        working_hours = self.request.user.get_working_hours()

        self.initial["start_date"] = timezone.make_aware(
            datetime.combine(
                (timezone.now().date() + timedelta(days=1)), working_hours["start"]
            )
        )
        self.initial["end_date"] = timezone.make_aware(
            datetime.combine(
                (timezone.now().date() + timedelta(days=1)), working_hours["end"]
            )
        )

        self.fields["type_of_leave"].label = False
        self.fields["type_of_leave"].choices = LeaveRequestTypes.FORM_CHOICES
        self.fields["notes"].label = False
        # self.fields["start_date"].widget = DateTimePickerInput(range_from="end_date")
        self.fields["start_date"].widget = DateTimePickerInput()
        self.fields["end_date"].widget = DateTimePickerInput()

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        today = timezone.now()

        if LeaveRequest.objects.filter(
            user=self.request.user,
            cancelled=False,
            start_date__lte=end,
            end_date__gte=start,
        ).exists():
            self.add_error(
                None, "Unable to save. The dates overlap an existing leave request."
            )

        if start < today:
            if not self.instance.id and "warn_override" not in self.data:
                self.add_error(
                    "start_date",
                    format_html(
                        "The start date is before today. Please save again to acknowledge."
                        '<input type="hidden" id="warn_override"'  # inject hidden input with error msg itself
                        'name="warn_override" value="0"/>'  # so it's returned in form `data` on second save
                    ),
                )

        if start > end:
            self.add_error("end_date", "The end date is before the start date.")

        # Now lets check if this takes us over our available leave
        unit = "day"
        days = businessDuration(start, end, unit=unit)
        requested_days = round(days, 2)
        available_days = self.request.user.remaining_leave()
        if requested_days > available_days:
            if config.LEAVE_ENFORCE_LIMIT:
                self.add_error(
                    None,
                    "You have requested more days than your allocation ({} required, {} available)".format(
                        str(requested_days), str(available_days)
                    ),
                )
            else:
                if not self.instance.id and "warn_override" not in self.data:
                    self.add_error(
                        None,
                        format_html(
                            "You have requested more days than your allocation. Are you sure you wish to continue? Please save again to acknowledge."
                            '<input type="hidden" id="warn_override"'  # inject hidden input with error msg itself
                            'name="warn_override" value="0"/>'  # so it's returned in form `data` on second save
                        ),
                    )

    class Meta:
        model = LeaveRequest
        fields = (
            "start_date",
            "end_date",
            "type_of_leave",
            "notes",
        )


class InviteUserForm(forms.ModelForm):
    invited_email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super(InviteUserForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Div(
                    FloatingField("invited_email"),
                    css_class="input-group input-group-dynamic",
                ),
            ),
            Div(
                StrictButton(
                    "Invite User", type="submit", css_class="btn btn-primary w-100 mb-3"
                ),
                css_class="button-row d-flex mt-4",
            ),
        )

    class Meta:
        model = UserInvitation
        fields = ("invited_email",)


class ChaoticaUserForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        self.invite = kwargs.pop("invite", None)
        super(ChaoticaUserForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if self.invite:
            self.fields["email"].initial = self.invite.invited_email
            self.fields["email"].disabled = True
        self.helper.layout = Layout(
            Row(
                Column(
                    Div(
                        FloatingField("first_name"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
                Column(
                    Div(
                        FloatingField("last_name"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
            ),
            Row(
                Div(
                    FloatingField("email"), css_class="input-group input-group-dynamic"
                ),
            ),
            Row(
                Column(
                    Div(
                        FloatingField("password1"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
                Column(
                    Div(
                        FloatingField("password2"),
                        css_class="input-group input-group-dynamic",
                    )
                ),
            ),
            Div(
                StrictButton(
                    "Create User", type="submit", css_class="btn btn-primary w-100 mb-3"
                ),
                css_class="button-row d-flex mt-4",
            ),
        )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "password1", "password2")
        widgets = {
            "first_name": forms.TextInput(attrs={"autofocus": True}),
        }


class MergeUserForm(forms.Form):
    user_to_merge = forms.ModelChoiceField(
        queryset=User.objects.filter(),
        required=True,
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super(MergeUserForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("user_to_merge", style="width: 100%;"),
        )

    class Meta:
        fields = ("user_to_merge",)


class AssignRoleForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(AssignRoleForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.fields["groups"].queryset = Group.objects.filter(
            name__startswith=settings.GLOBAL_GROUP_PREFIX
        )
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("groups", style="width: 100%;"),
        )

    class Meta:
        model = User
        widgets = {
            "groups": autocomplete.ModelSelect2Multiple(),
        }
        fields = ("groups",)


class ProfileForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "notification_email",
            "password1",
            "password2",
        )


class EditProfileForm(forms.ModelForm):

    profile_image = forms.FileField(
        label="Profile Image",
        required=False,
        validators=[validate_file_infection],
    )
    
    pref_timezone = forms.ChoiceField(
        choices=[(x, x) for x in pytz.common_timezones],
        widget=autocomplete.ModelSelect2(),
    )

    manager = forms.ModelChoiceField(
        queryset=User.objects.filter(),
        required=False,
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    acting_manager = forms.ModelChoiceField(
        queryset=User.objects.filter(),
        required=False,
        widget=autocomplete.ModelSelect2(
            url="user-autocomplete",
            attrs={
                "data-minimum-input-length": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.current_request = kwargs.pop("current_request", None)
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.fields["contracted_leave_renewal"].widget = DatePickerInput()
        usr = kwargs.get("instance")
        controlled_fields = [
            "manager",
            "acting_manager",
            "contracted_leave",
            "carry_over_leave",
            "contracted_leave_renewal",
        ]
        for f in controlled_fields:
            self.fields[f].disabled = True

        # Controlled fields:
        # - leave
        # - manager(s)

        if usr.has_manager():
            # Has manager so leave is sorted by them.
            if usr.pk == self.current_request.user.pk:
                messages.add_message(
                    self.current_request,
                    messages.INFO,
                    "You can not edit your own Work and Annual Leave Details while you have a manager.",
                )
            else:
                if usr.can_be_managed_by(self.current_request.user):
                    # We're not ourselves and we can manage them:
                    for f in controlled_fields:
                        self.fields[f].disabled = False
        else:
            # We don't have a manager. Let us edit our own fields...
            for f in controlled_fields:
                self.fields[f].disabled = False

        self.fields["show_help"].help_text = False
        self.fields["email"].disabled = True

    class Meta:
        model = User
        widgets = {
            "languages": autocomplete.ModelSelect2Multiple(),
        }
        fields = (
            "first_name",
            "last_name",
            "profile_image",
            "pref_timezone",
            "email",
            "notification_email",
            "phone_number",
            "manager",
            "acting_manager",
            "job_title",
            "show_help",
            "location",
            "country",
            "languages",
            "contracted_leave",
            "carry_over_leave",
            "contracted_leave_renewal",
        )

    def clean_profile_image(self):
        profile_image = self.cleaned_data["profile_image"]
        if profile_image:
            try:
                w, h = get_image_dimensions(profile_image)

                # validate dimensions
                max_width = max_height = 1024
                if (w and h) and (w > max_width or h > max_height):
                    self.add_error(
                        "profile_image",
                        "Please use an image that is "
                        "%s x %s pixels or smaller." % (max_width, max_height),
                    )

                # validate content type
                main, sub = profile_image.content_type.split("/")
                if not (main == "image" and sub in ["jpeg", "pjpeg", "gif", "png"]):
                    self.add_error(
                        "profile_image", "Please use a JPEG, GIF or PNG image."
                    )

                # validate file size
                if len(profile_image) > (1024 * 1024 *2):
                    self.add_error(
                        "profile_image", "Avatar file size may not exceed 2M."
                    )

            except AttributeError:
                """
                Handles case when we are updating the user profile
                and do not supply a new avatar
                """

        return profile_image


class ImportSiteDataForm(forms.Form):
    importFiles = forms.FileField(label="Data")
    importType = forms.ChoiceField(
        choices=[
            ("CSVUserImporter", "User CSV"),
            ("SmartSheetCSVImporter", "SmartSheet Project CSV"),
            ("ResourceManagerUserImporter", "Resource Manager User JSONs"),
            ("ResourceManagerProjectImporter", "Resource Manager Project JSON"),
        ]
    )

    def __init__(self, *args, **kwargs):
        super(ImportSiteDataForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Row(
                    Div(
                        Field("importType"), css_class="input-group input-group-dynamic"
                    )
                ),
                Row(
                    Div(
                        Field("importFiles", multiple=True),
                        css_class="input-group input-group-dynamic",
                    )
                ),
                css_class="modal-body pt-3",
            ),
            Div(
                Div(
                    StrictButton(
                        "Import",
                        type="submit",
                        css_class="btn btn-phoenix-warning ms-auto mb-0",
                    ),
                    css_class="button-row d-flex mt-4",
                ),
                css_class="modal-footer",
            ),
        )

    class Meta:
        fields = ("importType", "importFiles")
