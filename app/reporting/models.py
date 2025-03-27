from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.db.models.functions import Lower
from simple_history.models import HistoricalRecords

class ReportCategory(models.Model):
    """Categories for organizing reports (similar to SIMS categories)"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='report_categories'
    )
    
    class Meta:
        ordering = [Lower('name')]
        verbose_name_plural = "Report Categories"
    
    def __str__(self):
        return self.name

class Report(models.Model):
    """Stores report definitions"""
    PRESENTATION_CHOICES = [
        ('excel', 'Excel Spreadsheet'),
        ('html', 'Web Page (HTML)'),
        ('pdf', 'PDF Document'),
        ('text', 'Text File'),
        ('word', 'Word Document'),
        ('analysis', 'Analysis Report'),
    ]
    
    # Basic info
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        ReportCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reports'
    )
    is_private = models.BooleanField(
        default=True, 
        help_text="If unchecked, this report will be available to all users"
    )
    
    # Creator and ownership
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='created_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    
    # Report definition components
    data_area = models.CharField(
        max_length=100, 
        help_text="The primary data focus of the report (e.g. 'user', 'job', 'phase')"
    )
    population_filter = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Filters to refine the population (e.g. 'active users only')"
    )
    selected_fields = models.JSONField(
        default=list,
        help_text="List of fields/columns to display in the report"
    ) 
    filter_conditions = models.JSONField(
        default=list, 
        help_text="Filter conditions to apply to the report"
    )
    sort_order = models.JSONField(
        default=list,
        help_text="Fields to sort by and direction (asc/desc)"
    )
    
    # Presentation options
    default_presentation = models.CharField(
        max_length=20,
        choices=PRESENTATION_CHOICES,
        default='excel'
    )
    allow_runtime_presentation_choice = models.BooleanField(
        default=True,
        help_text="Allow users to choose output format at runtime"
    )
    presentation_options = models.JSONField(
        default=dict,
        help_text="Format-specific presentation options"
    )
    
    # Tracking
    history = HistoricalRecords()
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('reporting:report_detail', kwargs={'pk': self.pk})
    
    def run(self, user, params=None):
        """Execute the report with optional runtime parameters"""
        from reporting.engine import ReportEngine
        
        engine = ReportEngine(self, user)
        return engine.execute(params)

class ReportSchedule(models.Model):
    """Schedule for automated report generation"""
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    report = models.ForeignKey(
        Report, 
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    
    # Scheduling details
    day_of_week = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Day of week (0-6, where 0 is Monday) for weekly schedules"
    )
    day_of_month = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Day of month (1-31) for monthly schedules"
    )
    
    # Recipients
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='report_subscriptions'
    )
    
    # Email options
    email_subject = models.CharField(max_length=255, blank=True)
    email_body = models.TextField(blank=True)
    include_as_attachment = models.BooleanField(default=True)
    
    # Parameters
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Runtime parameters to apply when generating the report"
    )
    
    # Tracking
    last_run = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='created_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.report.name})"
    
    def mark_as_run(self):
        self.last_run = timezone.now()
        self.save(update_fields=['last_run'])

class SavedReportOutput(models.Model):
    """Stores generated report outputs"""
    report = models.ForeignKey(
        Report, 
        on_delete=models.CASCADE,
        related_name='outputs'
    )
    schedule = models.ForeignKey(
        ReportSchedule, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='outputs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL,
        null=True,
        related_name='report_outputs'
    )
    
    # The actual report content
    file = models.FileField(upload_to='reports/%Y/%m/')
    format = models.CharField(max_length=20)
    file_size = models.PositiveIntegerField(default=0)
    
    # Parameters used
    parameters = models.JSONField(
        default=dict,
        blank=True
    )
    
    def __str__(self):
        return f"{self.report.name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"