from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, path
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from .models import (
    Notification,
    NotificationSubscription,
    NotificationCategory,
    SubscriptionRule,
    GlobalRoleCriteria,
    OrgUnitRoleCriteria,
    JobRoleCriteria,
    PhaseRoleCriteria,
    DynamicRuleCriteria,
    EmailTemplate,
)

class GlobalRoleCriteriaInline(admin.TabularInline):
    model = GlobalRoleCriteria
    extra = 0
    fields = ('role',)

class OrgUnitRoleCriteriaInline(admin.TabularInline):
    model = OrgUnitRoleCriteria
    extra = 0
    fields = ('unit_role',)
    raw_id_fields = ('unit_role',)

class JobRoleCriteriaInline(admin.TabularInline):
    model = JobRoleCriteria
    extra = 0
    fields = ('role_id', 'role_display')
    readonly_fields = ('role_display',)
    
    def role_display(self, obj):
        role_dict = dict(JobRoleCriteria.JOB_ROLES)
        return role_dict.get(obj.role_id, "Unknown")
    role_display.short_description = 'Role'

class PhaseRoleCriteriaInline(admin.TabularInline):
    model = PhaseRoleCriteria
    extra = 0
    fields = ('role_id', 'role_display')
    readonly_fields = ('role_display',)
    
    def role_display(self, obj):
        role_dict = dict(JobRoleCriteria.PHASE_ROLES)
        return role_dict.get(obj.role_id, "Unknown")
    role_display.short_description = 'Role'

class DynamicRuleCriteriaInline(admin.TabularInline):
    model = DynamicRuleCriteria
    extra = 0
    fields = ('criteria_name', 'parameters')
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'criteria_name':
            from .criteria_registry import _CRITERIA_REGISTRY
            kwargs['widget'] = admin.widgets.AdminTextInputWidget()
            kwargs['widget'].choices = [(k, k) for k in _CRITERIA_REGISTRY.keys()]
        return super().formfield_for_dbfield(db_field, **kwargs)

@admin.register(SubscriptionRule)
class SubscriptionRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'get_notification_type_display', 
        'is_active', 
        'priority', 
        'get_criteria_count',
        'get_subscriptions_count',
        'updated_at'
    ]
    list_filter = ['notification_type', 'is_active']
    search_fields = ['name', 'description']
    inlines = [
        GlobalRoleCriteriaInline,
        OrgUnitRoleCriteriaInline,
        JobRoleCriteriaInline,
        PhaseRoleCriteriaInline,
        DynamicRuleCriteriaInline
    ]
    
    def get_notification_type_display(self, obj):
        from .enums import NotificationTypes
        choices_dict = dict(NotificationTypes.CHOICES)
        return choices_dict.get(obj.notification_type, f"Unknown ({obj.notification_type})")
    get_notification_type_display.short_description = 'Notification Type'
    
    def get_criteria_count(self, obj):
        global_count = obj.globalrolecriteria_criteria.count()
        org_count = obj.orgunitrolecriteria_criteria.count()
        job_count = obj.jobrolecriteria_criteria.count()
        dynamic_count = obj.dynamicrulecriteria_criteria.count()
        total = global_count + org_count + job_count + dynamic_count
        return format_html(
            '<span title="Global: {}, Org: {}, Job: {}, Dynamic: {}">{}</span>',
            global_count, org_count, job_count, dynamic_count, total
        )
    get_criteria_count.short_description = 'Criteria'
    
    def get_subscriptions_count(self, obj):
        count = NotificationSubscription.objects.filter(
            notification_type=obj.notification_type,
            created_by_rule=True
        ).count()
        return count
    get_subscriptions_count.short_description = 'Subscriptions'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related(
            'globalrolecriteria_criteria',
            'orgunitrolecriteria_criteria',
            'jobrolecriteria_criteria',
            'dynamicrulecriteria_criteria'
        )
        return qs

# Enhance the NotificationSubscription admin
class SubscriptionRuleFilter(admin.SimpleListFilter):
    title = 'Creation Method'
    parameter_name = 'creation_method'
    
    def lookups(self, request, model_admin):
        return (
            ('rule', 'Created by Rule'),
            ('manual', 'Created Manually'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'rule':
            return queryset.filter(created_by_rule=True)
        if self.value() == 'manual':
            return queryset.filter(created_by_rule=False)
        return queryset

@admin.register(NotificationSubscription)
class NotificationSubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 
        'get_notification_type_display', 
        'entity_type', 
        'entity_id', 
        'email_enabled', 
        'in_app_enabled',
        'creation_method'
    ]
    list_filter = [
        'notification_type', 
        'entity_type', 
        'email_enabled', 
        'in_app_enabled',
        SubscriptionRuleFilter
    ]
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    
    def get_notification_type_display(self, obj):
        from .enums import NotificationTypes
        choices_dict = dict(NotificationTypes.CHOICES)
        return choices_dict.get(obj.notification_type, f"Unknown ({obj.notification_type})")
    get_notification_type_display.short_description = 'Notification Type'
    
    def creation_method(self, obj):
        return "Auto-Rule" if obj.created_by_rule else "Manual"
    creation_method.short_description = 'Creation Method'

# Keep existing admin registrations
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "timestamp", "title", "is_emailed", "should_email", "read"]
    list_filter = ["is_emailed", "should_email", "read", "notification_type"]
    search_fields = ["title", "message", "user__username", "user__first_name", "user__last_name"]
    actions = ["mark_as_emailed", "send_email_now"]

    @admin.action(description="Mark selected as emailed (without sending)")
    def mark_as_emailed(self, request, queryset):
        count = queryset.update(is_emailed=True)
        self.message_user(request, f"{count} notification(s) marked as emailed.")

    @admin.action(description="Send email now")
    def send_email_now(self, request, queryset):
        sent = 0
        failed = 0
        for notification in queryset.filter(should_email=True):
            try:
                notification.send_email(resend=True)
                sent += 1
            except Exception:
                failed += 1
        self.message_user(request, f"{sent} email(s) sent, {failed} failed.")

@admin.register(NotificationCategory)
class NotificationCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']


# A fixed, safe dummy context for previews - never uses real data.
_PREVIEW_CONTEXT = {
    'title': 'Example subject line',
    'message': 'This is a preview of the email content with sample data.',
    'action_link': 'https://example.com/action',
    'user': 'Sample User',
    'icon': '',
    'SITE_DOMAIN': 'chaotica.example.com',
    'SITE_PROTO': 'https',
}


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'is_customized', 'extends_base', 'updated_at', 'preview_link']
    list_filter = ['is_active', 'extends_base', 'is_customized']
    search_fields = ['name', 'slug', 'description']
    readonly_fields = ['slug', 'is_seeded', 'created_at', 'updated_at']
    fieldsets = [
        (None, {'fields': ['slug', 'name', 'description', 'is_active']}),
        ('Content', {'fields': ['subject', 'body_html', 'body_text', 'extends_base', 'action_label']}),
        ('Help', {'fields': ['available_context'], 'classes': ['collapse']}),
        ('Meta', {'fields': ['is_seeded', 'is_customized', 'created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    # Editing raw template source is a template-injection surface; restrict to
    # superusers. Everyone with staff access can still view.
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        # A human edit marks the row customised so re-seeding won't clobber it.
        if change:
            obj.is_customized = True
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/preview/',
                self.admin_site.admin_view(self.preview_view),
                name='notifications_emailtemplate_preview',
            ),
        ]
        return custom + urls

    def preview_link(self, obj):
        if not obj.pk:
            return ''
        url = reverse('admin:notifications_emailtemplate_preview', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Preview</a>', url)
    preview_link.short_description = 'Preview'

    def preview_view(self, request, pk):
        template = get_object_or_404(EmailTemplate, pk=pk)
        _, html, _ = template.render(_PREVIEW_CONTEXT)
        return HttpResponse(html)