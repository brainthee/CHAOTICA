# notifications/admin.py (extended)

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count

from .models import (
    Notification, 
    NotificationSubscription, 
    NotificationCategory,
    SubscriptionRule,
    GlobalRoleCriteria,
    OrgUnitRoleCriteria,
    JobRoleCriteria,
    PhaseRoleCriteria,
    DynamicRuleCriteria
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
        return dict(NotificationTypes.CHOICES)[obj.notification_type]
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
        # This requires adding a created_by_rule field to NotificationSubscription
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
        return dict(NotificationTypes.CHOICES)[obj.notification_type]
    get_notification_type_display.short_description = 'Notification Type'
    
    def creation_method(self, obj):
        return "Auto-Rule" if obj.created_by_rule else "Manual"
    creation_method.short_description = 'Creation Method'

# Keep existing admin registrations
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "timestamp", "title", "is_emailed"]

@admin.register(NotificationCategory)
class NotificationCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']