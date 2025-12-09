from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from django.utils.html import format_html
from django import forms
from ..models import LeaveRequest, User, Group, UserInvitation, Holiday, Language
from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import (
    StrictButton,
)
from crispy_forms.layout import Layout, Row, Column, Field, Div, HTML
from crispy_bootstrap5.bootstrap5 import FloatingField
from django_countries.widgets import CountrySelectWidget
from django_countries.fields import CountryField
from constance.admin import ConstanceForm
from django_select2 import forms as s2forms
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
import tempfile
import os
import gzip
import logging
from django.core.exceptions import ValidationError
import tarfile
from cities_light.models import City



MAX_BACKUP_SIZE = getattr(settings, 'MAX_BACKUP_SIZE', 500 * 1024 * 1024)  # 500MB default

class DatabaseRestoreForm(forms.Form):
    backup_file = forms.FileField(
        label='Backup File',
        help_text='Select a .gz database backup file',
        required=True
    )
    confirm = forms.BooleanField(
        label='I understand this will overwrite the current database',
        help_text='This action cannot be undone. All current data will be replaced.',
        required=False  # We'll handle this separately for the two-step process
    )

    db_confirmed_restore = forms.BooleanField(
        widget=forms.HiddenInput(), required=False, initial=False
    )
    
    def __init__(self, *args, **kwargs):
        super(DatabaseRestoreForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(
                    Field("backup_file"),
                    css_class="input-group input-group-dynamic",
                ),
                Column(
                    Field("confirm"),
                    css_class="input-group input-group-dynamic",
                ),
            ),
            Row(
                Field("db_confirmed_restore"),
                StrictButton(
                    "Restore Database", type="submit", id="db-restore-submit-btn", css_class="btn btn-danger w-100 mb-3"
                ),
            ),
        )

    def clean_backup_file(self):
        backup_file = self.cleaned_data['backup_file']
        
        # Check file size
        if backup_file.size > MAX_BACKUP_SIZE:
            max_size_mb = MAX_BACKUP_SIZE / (1024 * 1024)
            raise ValidationError(
                f'File too large. Maximum size is {max_size_mb:.1f}MB. '
                f'Your file is {backup_file.size / (1024 * 1024):.1f}MB.'
            )
        
        # Check file extension
        if not backup_file.name.endswith('.gz'):
            raise ValidationError(
                'Invalid file extension. File must be a .gz (gzip) backup file.'
            )
        
        # Save to temporary file for gzip validation
        with tempfile.NamedTemporaryFile(delete=False, suffix='.gz') as tmp_file:
            for chunk in backup_file.chunks():
                tmp_file.write(chunk)
            temp_path = tmp_file.name
        
        # Validate gzip format
        try:
            with gzip.open(temp_path, 'rb') as gz_file:
                # Try to read first 1KB to verify it's valid
                test_data = gz_file.read(1024)
                if not test_data:
                    raise ValidationError('Backup file appears to be empty.')
        except gzip.BadGzipFile:
            raise ValidationError(
                'Invalid gzip file. Please upload a valid database backup file.'
            )
        except Exception as e:
            raise ValidationError(f'Error validating backup file: {str(e)}')
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        return backup_file
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Only enforce confirmation if we're in the confirmation step
        if self.data.get('confirmed_restore') == 'true' and not cleaned_data.get('confirm'):
            raise ValidationError({
                'confirm': 'You must confirm that you understand this action will overwrite the database.'
            })
        
        return cleaned_data


MAX_BACKUP_SIZE = getattr(settings, 'MAX_BACKUP_SIZE', 500 * 1024 * 1024)  # 500MB default
MAX_MEDIA_BACKUP_SIZE = getattr(settings, 'MAX_MEDIA_BACKUP_SIZE', 2 * 1024 * 1024 * 1024)  # 2GB default for media

class MediaRestoreForm(forms.Form):
    backup_file = forms.FileField(
        label='Media Backup File',
        help_text='Select a .tar.gz media backup file',
        required=True
    )
    confirm = forms.BooleanField(
        label='I understand this will overwrite the current media files',
        help_text='This action cannot be undone. All current media files will be replaced.',
        required=False
    )

    media_confirmed_restore = forms.BooleanField(
        widget=forms.HiddenInput(), required=False, initial=False
    )
    
    def __init__(self, *args, **kwargs):
        super(MediaRestoreForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(
                    Field("backup_file"),
                    css_class="input-group input-group-dynamic",
                ),
                Column(
                    Field("confirm"),
                    css_class="input-group input-group-dynamic",
                ),
            ),
            Row(
                Field("media_confirmed_restore"),
                StrictButton(
                    "Restore Media", type="submit", id="media-restore-submit-btn", css_class="btn btn-danger w-100 mb-3"
                ),
            ),
        )
    
    def clean_backup_file(self):
        backup_file = self.cleaned_data['backup_file']
        
        # Check file size (larger limit for media)
        if backup_file.size > MAX_MEDIA_BACKUP_SIZE:
            max_size_gb = MAX_MEDIA_BACKUP_SIZE / (1024 * 1024 * 1024)
            raise ValidationError(
                f'File too large. Maximum size is {max_size_gb:.1f}GB. '
                f'Your file is {backup_file.size / (1024 * 1024 * 1024):.2f}GB.'
            )
        
        # Check file extension
        if not (backup_file.name.endswith('.tar.gz') or backup_file.name.endswith('.tgz')):
            raise ValidationError(
                'Invalid file extension. File must be a .tar.gz or .tgz (compressed tar) backup file.'
            )
        
        # Save to temporary file for validation
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
            for chunk in backup_file.chunks():
                tmp_file.write(chunk)
            temp_path = tmp_file.name
        
        # Validate tar.gz format
        try:
            # First check if it's a valid gzip
            with gzip.open(temp_path, 'rb') as gz_file:
                # Try to read a small amount
                test_data = gz_file.read(512)  # tar header is 512 bytes
                if not test_data:
                    raise ValidationError('Media backup file appears to be empty.')
            
            # Then check if it's a valid tar file
            with tarfile.open(temp_path, 'r:gz') as tar:
                # Just try to read the members list
                members = tar.getmembers()
                if not members:
                    raise ValidationError('Media backup archive is empty.')
                    
        except gzip.BadGzipFile:
            raise ValidationError(
                'Invalid compressed file. Please upload a valid .tar.gz media backup file.'
            )
        except tarfile.TarError as e:
            raise ValidationError(
                f'Invalid tar archive: {str(e)}. Please upload a valid media backup file.'
            )
        except Exception as e:
            raise ValidationError(f'Error validating media backup file: {str(e)}')
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        return backup_file
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Only enforce confirmation if we're in the confirmation step
        if self.data.get('confirmed_restore') == 'true' and not cleaned_data.get('confirm'):
            raise ValidationError({
                'confirm': 'You must confirm that you understand this action will overwrite the media files.'
            })
        
        return cleaned_data
    

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
                        Field("CHRISTMAS_LIGHTS_ENABLED"),
                        css_class="input-group input-group-dynamic",
                    ),
                    Div(
                        Field("CHRISTMAS_TREE_ENABLED"),
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
                        Field("MAINTENANCE_MODE"),
                        css_class="input-group input-group-dynamic",
                    ),
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
                (timezone.now().date() + timedelta(weeks=4)), working_hours["end"]
            )
        )

        self.fields["type_of_leave"].label = False
        self.fields["type_of_leave"].choices = LeaveRequestTypes.FORM_CHOICES
        self.fields["notes"].label = False

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
        widgets = {
            "start_date": DateTimePickerInput(options={"allowInputToggle": True}),
            "end_date": DateTimePickerInput(
                # range_from="start_date", 
                options={"allowInputToggle": True}
            ),
        }


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
        widget=s2forms.ModelSelect2Widget(
            attrs={
                'class': 'select2-widget',
                'data-minimum-input-length': 3,
                'data-ajax--url': '/autocomplete/users',
                'data-ajax--cache': 'true',
                'data-ajax--type': 'GET',
            },
            search_fields=['first_name__icontains', 'last_name__icontains', 'email__icontains'],
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

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.filter(),
        required=False,
        widget=s2forms.Select2MultipleWidget(
            attrs={
                'class': 'select2-widget',
                'data-minimum-input-length': 0,
            },
        ),
    )


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
    )
    
    pref_timezone = forms.ChoiceField(
        choices=[(x, x) for x in pytz.common_timezones],
        widget=s2forms.Select2Widget(),
    )

    languages = forms.ModelMultipleChoiceField(
        queryset=Language.objects.filter(),
        required=False,
        widget=s2forms.ModelSelect2MultipleWidget(
            attrs={
                'class': 'select2-widget',
            },
            search_fields=['display_name__icontains', 'lang_code__icontains'],
        ),
    )

    manager = forms.ModelChoiceField(
        queryset=User.objects.filter(),
        required=False,
        widget=s2forms.ModelSelect2Widget(
            attrs={
                'class': 'select2-widget',
                'data-minimum-input-length': 3,
                'data-ajax--url': '/autocomplete/users',
                'data-ajax--cache': 'true',
                'data-ajax--type': 'GET',
            },
            search_fields=['first_name__icontains', 'last_name__icontains', 'email__icontains'],
        ),
    )

    city = forms.ModelChoiceField(
        queryset=City.objects.filter(),
        required=False,
        widget=s2forms.ModelSelect2Widget(
            attrs={
                'class': 'select2-widget',
                'data-placeholder': 'Select your city...',
            },
            search_fields=['name__icontains', 'search_names__icontains'],
        ),
    )

    def __init__(self, *args, **kwargs):
        self.current_request = kwargs.pop("current_request", None)
        super(EditProfileForm, self).__init__(*args, **kwargs)

        if getattr(settings, 'CLAMAV_ENABLED', True):
            self.fields['profile_image'].validators.append(validate_file_infection)

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
            "alias",
            "city",
            "show_help",
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
