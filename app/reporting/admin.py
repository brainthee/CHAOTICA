from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count

from .models import Report, ReportCategory, ReportSchedule, SavedReportOutput


@admin.register(ReportCategory)
class ReportCategoryAdmin(admin.ModelAdmin):
    """Admin configuration for ReportCategory model"""
    list_display = ('name', 'description', 'created_at', 'created_by', 'report_count')
    search_fields = ('name', 'description')
    list_filter = ('created_at',)
    readonly_fields = ('created_at',)
    fieldsets = (
        (None, {
            'fields': ('name', 'description')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def report_count(self, obj):
        """Show count of reports in this category"""
        count = obj.reports.count()
        return format_html('<a href="{}?category={}">{} reports</a>', 
                          reverse('admin:reporting_report_changelist'), 
                          obj.id, count)
    report_count.short_description = 'Reports'
    
    def get_queryset(self, request):
        """Add report count annotation"""
        queryset = super().get_queryset(request)
        return queryset.annotate(report_count=Count('reports'))
    
    def save_model(self, request, obj, form, change):
        """Set created_by when creating new category"""
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class ReportScheduleInline(admin.TabularInline):
    """Inline for report schedules"""
    model = ReportSchedule
    extra = 0
    fields = ('name', 'enabled', 'frequency', 'last_run', 'recipient_count')
    readonly_fields = ('last_run', 'recipient_count')
    
    def recipient_count(self, obj):
        """Show count of recipients"""
        if obj.id:
            count = obj.recipients.count()
            return format_html('{} recipients', count)
        return '0 recipients'
    recipient_count.short_description = 'Recipients'


class SavedOutputInline(admin.TabularInline):
    """Inline for saved report outputs"""
    model = SavedReportOutput
    extra = 0
    fields = ('created_at', 'created_by', 'format', 'file_size_display', 'download_link')
    readonly_fields = ('created_at', 'created_by', 'format', 'file_size_display', 'download_link')
    max_num = 5
    can_delete = False
    
    def file_size_display(self, obj):
        """Format file size in human-readable format"""
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
            return f"{obj.file_size / (1024 * 1024):.1f} MB"
    file_size_display.short_description = 'File Size'
    
    def download_link(self, obj):
        """Provide download link for the file"""
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.file.url)
        return '-'
    download_link.short_description = 'Download'


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Admin configuration for Report model"""
    list_display = ('name', 'category', 'data_area', 'created_by', 'created_at', 'modified_at', 'is_private', 'output_count')
    list_filter = ('is_private', 'data_area', 'category', 'created_at', 'modified_at')
    search_fields = ('name', 'description', 'created_by__email', 'created_by__first_name', 'created_by__last_name')
    readonly_fields = ('created_at', 'modified_at', 'run_report')
    inlines = [ReportScheduleInline, SavedOutputInline]
    
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'category', 'is_private')
        }),
        ('Report Definition', {
            'fields': ('data_area', 'population_filter', 'selected_fields', 
                      'filter_conditions', 'sort_order'),
            'classes': ('collapse',)
        }),
        ('Presentation Options', {
            'fields': ('default_presentation', 'allow_runtime_presentation_choice', 
                      'presentation_options'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'modified_at'),
            'classes': ('collapse',)
        }),
        ('Actions', {
            'fields': ('run_report',),
        }),
    )
    
    def output_count(self, obj):
        """Show count of report outputs"""
        count = obj.outputs.count()
        if count > 0:
            return format_html('<a href="{}?report__id__exact={}">{} outputs</a>', 
                            reverse('admin:reporting_savedreportoutput_changelist'), 
                            obj.id, count)
        return '0 outputs'
    output_count.short_description = 'Outputs'
    
    def run_report(self, obj):
        """Provide a link to run the report"""
        if obj.id:
            return format_html('<a class="button" href="{}" target="_blank">Run Report</a>', 
                            reverse('reporting:report_run', args=[obj.id]))
        return '-'
    run_report.short_description = 'Run Report'
    
    def get_queryset(self, request):
        """Add output count annotation"""
        queryset = super().get_queryset(request)
        return queryset.annotate(output_count=Count('outputs'))


@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    """Admin configuration for ReportSchedule model"""
    list_display = ('name', 'report', 'frequency', 'enabled', 'last_run', 'next_run_display', 'recipient_count')
    list_filter = ('frequency', 'enabled', 'last_run')
    search_fields = ('name', 'report__name', 'email_subject')
    readonly_fields = ('last_run', 'next_run_display', 'created_at', 'created_by')
    
    fieldsets = (
        (None, {
            'fields': ('name', 'report', 'enabled')
        }),
        ('Schedule Details', {
            'fields': ('frequency', 'day_of_week', 'day_of_month', 'last_run', 'next_run_display')
        }),
        ('Email Settings', {
            'fields': ('recipients', 'email_subject', 'email_body', 'include_as_attachment')
        }),
        ('Parameters', {
            'fields': ('parameters',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def recipient_count(self, obj):
        """Show count of recipients"""
        count = obj.recipients.count()
        names = ", ".join([f"{u.first_name} {u.last_name}" for u in obj.recipients.all()[:3]])
        if count > 3:
            names += f" and {count - 3} more"
        return f"{count} ({names})"
    recipient_count.short_description = 'Recipients'
    
    def next_run_display(self, obj):
        """Calculate and display the next run time"""
        next_run = obj.get_next_run() if hasattr(obj, 'get_next_run') else None
        if next_run:
            return next_run.strftime('%Y-%m-%d %H:%M')
        return 'Unknown'
    next_run_display.short_description = 'Next Run'


@admin.register(SavedReportOutput)
class SavedReportOutputAdmin(admin.ModelAdmin):
    """Admin configuration for SavedReportOutput model"""
    list_display = ('report', 'format', 'created_at', 'created_by', 'file_size_display', 'download_link')
    list_filter = ('format', 'created_at')
    search_fields = ('report__name', 'created_by__email')
    readonly_fields = ('report', 'format', 'created_at', 'created_by', 'file', 'file_size_display', 'download_link')
    
    fieldsets = (
        (None, {
            'fields': ('report', 'format', 'file')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'file_size_display')
        }),
        ('Parameters', {
            'fields': ('parameters',),
            'classes': ('collapse',)
        }),
    )
    
    def file_size_display(self, obj):
        """Format file size in human-readable format"""
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
            return f"{obj.file_size / (1024 * 1024):.1f} MB"
    file_size_display.short_description = 'File Size'
    
    def download_link(self, obj):
        """Provide download link for the file"""
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.file.url)
        return '-'
    download_link.short_description = 'Download'