from django.db import models
from django.conf import settings
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
import uuid
import json

class ReportCategory(models.Model):
    """Categories for organizing reports"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Report Categories'


class Report(models.Model):
    """Main report model that stores report definitions"""
    PRESENTATION_CHOICES = [
        ('excel', 'Excel Spreadsheet'),
        ('pdf', 'PDF Document'),
        ('html', 'Web Page (HTML)'),
        ('csv', 'CSV File'),
        ('word', 'Word Document'),
        ('text', 'Text File'),
        ('analysis', 'Analysis View'),
    ]
    
    # Basic information
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_reports')
    category = models.ForeignKey(ReportCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')
    is_private = models.BooleanField(default=True, help_text="Private reports are only visible to the owner")
    
    # Report focus/data area details
    data_area = models.ForeignKey('DataArea', on_delete=models.CASCADE, related_name='reports')
    
    # Output format and presentation
    presentation_type = models.CharField(max_length=50, choices=PRESENTATION_CHOICES, default='excel')
    presentation_options = models.JSONField(default=dict, blank=True, help_text="Specific options for the selected presentation type")
    allow_presentation_choice = models.BooleanField(default=False, help_text="Allow users to select the output format at runtime")
    
    # Tracking details
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    # Relationships
    favorites = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='favorite_reports', blank=True)
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('reporting:report_detail', kwargs={'uuid': self.uuid})
    
    def run_url(self):
        return reverse('reporting:run_report', kwargs={'uuid': self.uuid})
    
    def edit_url(self):
        return reverse('reporting:edit_report', kwargs={'uuid': self.uuid})
    
    def is_owned_by(self, user):
        return self.owner == user
    
    def can_view(self, user):
        """Check if user can view this report"""
        if user.is_superuser:
            return True
        if self.owner == user:
            return True
        if not self.is_private:
            return True
        return False
    
    def can_edit(self, user):
        """Check if user can edit this report"""
        if user.is_superuser:
            return True
        if self.owner == user:
            return True
        return False
    
    def get_fields(self):
        """Get all fields for this report in their proper order"""
        return self.fields.all().order_by('position')
    
    def get_filters(self):
        """Get all filters for this report"""
        return self.filters.all()
    
    def get_sorts(self):
        """Get all sort orders for this report in their proper order"""
        return self.sorts.all().order_by('position')
    
    class Meta:
        ordering = ['-updated_at']
        permissions = (
            ('can_run_all_reports', 'Can run all reports regardless of ownership'),
            ('can_share_reports', 'Can make reports publicly available'),
        )


class ReportField(models.Model):
    """Represents a column in a report"""
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='fields')
    data_field = models.ForeignKey('DataField', on_delete=models.CASCADE, related_name='report_fields')
    position = models.PositiveIntegerField(default=0)
    custom_label = models.CharField(max_length=255, blank=True, null=True)
    display_format = models.CharField(max_length=255, blank=True, null=True, 
                                      help_text="Optional format string for rendering this field")
    
    def __str__(self):
        if self.custom_label:
            return f"{self.custom_label} ({self.data_field})"
        return str(self.data_field)
    
    def get_display_name(self):
        """Get the display name for this field (custom or default)"""
        if self.custom_label:
            return self.custom_label
        return self.data_field.name
    
    class Meta:
        ordering = ['position']


class ReportFilter(models.Model):
    """Represents a filter condition for a report"""
    OPERATOR_CHOICES = [
        ('and', 'AND'),
        ('or', 'OR'),
    ]
    
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='filters')
    data_field = models.ForeignKey('DataField', on_delete=models.CASCADE, related_name='report_filters')
    filter_type = models.ForeignKey('FilterType', on_delete=models.CASCADE)
    value = models.TextField(blank=True, null=True)
    prompt_text = models.CharField(max_length=255, blank=True, null=True)
    prompt_at_runtime = models.BooleanField(default=False)
    
    # For complex filter groups
    parent_filter = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='child_filters')
    operator = models.CharField(max_length=3, choices=OPERATOR_CHOICES, default='and')
    position = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        if self.prompt_at_runtime:
            return f"{self.data_field} - [Prompt: {self.prompt_text}]"
        return f"{self.data_field} {self.filter_type} {self.value}"
    
    class Meta:
        ordering = ['position']


class ReportSort(models.Model):
    """Represents a sort order for a report"""
    DIRECTION_CHOICES = [
        ('asc', 'Ascending'),
        ('desc', 'Descending'),
    ]
    
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='sorts')
    data_field = models.ForeignKey('DataField', on_delete=models.CASCADE, related_name='report_sorts')
    direction = models.CharField(max_length=4, choices=DIRECTION_CHOICES, default='asc')
    position = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return f"{self.data_field} ({self.get_direction_display()})"
    
    class Meta:
        ordering = ['position']