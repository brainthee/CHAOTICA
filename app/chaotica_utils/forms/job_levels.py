from django_select2 import forms as s2forms
from django import forms
from django.core.exceptions import ValidationError
from ..models import JobLevel, UserJobLevel, User
from django.utils import timezone


class JobLevelForm(forms.ModelForm):
    """Form for creating and editing job levels"""

    class Meta:
        model = JobLevel
        fields = ['short_label', 'long_label', 'order', 'is_active']
        widgets = {
            'short_label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., CL1, CL2',
                'maxlength': '10'
            }),
            'long_label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Career Level 1 - Senior Manager',
                'maxlength': '100'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        help_texts = {
            'short_label': 'Brief identifier for the level (max 10 characters)',
            'long_label': 'Full description of the level (max 100 characters)',
            'order': 'Sort order - lower numbers = higher levels (e.g., CL1=1, CL5=5)',
            'is_active': 'Whether this level is currently available for assignment'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make long_label required in the form even though it's optional in the model
        self.fields['long_label'].required = True

        # If creating new, suggest next order
        if not self.instance.pk:
            self.fields['order'].initial = JobLevel.get_next_order()

    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order and order <= 0:
            raise ValidationError("Order must be a positive number")

        # Check for duplicate order (excluding current instance if editing)
        qs = JobLevel.objects.filter(order=order)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Order {order} is already taken")

        return order

    def clean_short_label(self):
        short_label = self.cleaned_data.get('short_label')

        # Check for duplicate short_label (excluding current instance if editing)
        qs = JobLevel.objects.filter(short_label=short_label)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Job level with short label '{short_label}' already exists")

        return short_label


class AssignJobLevelForm(forms.ModelForm):
    """Form for assigning a job level to a user"""
    user = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(is_active=True),
        widget=s2forms.ModelSelect2Widget(
            attrs={
                'class': 'select2-widget',
                'data-minimum-input-length': 3,
                'data-ajax--url': '/autocomplete/users',
                'data-ajax--cache': 'true',
                'data-ajax--type': 'GET',
            },
        ),
    )

    class Meta:
        model = UserJobLevel
        fields = ['user', 'job_level', 'assigned_date', 'notes']
        widgets = {
            'job_level': forms.Select(attrs={
                'class': 'form-select'
            }),
            'assigned_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional notes about this assignment/promotion...'
            })
        }
        help_texts = {
            'job_level': 'Choose the career level to assign',
            'assigned_date': 'Leave blank to use today\'s date',
            'notes': 'Add any relevant notes about this level assignment'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only show active job levels
        self.fields['job_level'].queryset = JobLevel.objects.filter(
            is_active=True
        ).order_by('order')

        # Make assigned_date not required (will default to today)
        self.fields['assigned_date'].required = False

    def clean_assigned_date(self):
        assigned_date = self.cleaned_data.get('assigned_date')
        if not assigned_date:
            assigned_date = timezone.now().date()
        elif assigned_date > timezone.now().date():
            raise ValidationError("Assignment date cannot be in the future")
        return assigned_date

    def save(self, commit=True):
        """Override save to handle user assignment"""

        # Ensure this is set as current (model's save method will handle unsetting others)
        self.instance.is_current = True

        return super().save(commit=commit)


class UpdateUserJobLevelForm(forms.Form):
    """Simplified form for updating a user's job level in the profile page"""

    job_level_id = forms.ModelChoiceField(
        queryset=JobLevel.objects.filter(is_active=True).order_by('order'),
        required=False,
        empty_label="No change",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    job_level_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes about this level change...'
        })
    )

    clear_job_level = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class ImportJobLevelAssignmentsForm(forms.Form):
    """Form for importing job level assignments via CSV"""

    csv_file = forms.FileField(
        label='CSV File',
        help_text='Upload a CSV file with columns: email, job_level_short_label, assigned_date (YYYY-MM-DD)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv'
        })
    )

    update_existing = forms.BooleanField(
        required=False,
        initial=True,
        label='Update Existing Assignments',
        help_text='If checked, will update existing user job levels. If unchecked, will skip users who already have a job level assigned.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def clean_csv_file(self):
        """Validate the CSV file"""
        csv_file = self.cleaned_data.get('csv_file')

        if not csv_file:
            raise ValidationError("Please select a CSV file")

        # Check file extension
        if not csv_file.name.endswith('.csv'):
            raise ValidationError("File must be a CSV file")

        # Check file size (limit to 5MB)
        if csv_file.size > 5 * 1024 * 1024:
            raise ValidationError("File size must be less than 5MB")

        return csv_file