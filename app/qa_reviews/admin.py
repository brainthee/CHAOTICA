from django.contrib import admin
from .models import QAReview, QAReviewConfiguration


@admin.register(QAReview)
class QAReviewAdmin(admin.ModelAdmin):
    list_display = ['phase', 'reviewer', 'reviewed_user', 'status', 'started_at', 'completed_at']
    list_filter = ['status', 'started_at', 'completed_at']
    search_fields = ['phase__phase_id', 'reviewer__username', 'reviewed_user__username', 'notes']
    readonly_fields = ['id', 'started_at']
    date_hierarchy = 'started_at'
    fieldsets = [
        ('Review Details', {
            'fields': ('phase', 'reviewer', 'reviewed_user', 'status', 'weeks_back_config')
        }),
        ('Timeline', {
            'fields': ('started_at', 'completed_at')
        }),
        ('Feedback', {
            'fields': ('notes',)
        })
    ]


@admin.register(QAReviewConfiguration)
class QAReviewConfigurationAdmin(admin.ModelAdmin):
    list_display = ['unit', 'weeks_back', 'enabled']
    list_filter = ['enabled']
    search_fields = ['unit__name']
