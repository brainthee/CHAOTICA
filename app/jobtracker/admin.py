from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Phase,
    Job,
    JobSupportTeamRole,
    SupportBudgetDraw,
    OrganisationalUnit,
    OrganisationalUnitMember,
    OrganisationalUnitSupportTemplateMember,
    SupportProfile,
    Team, TeamMember,
    Skill,
    SkillCategory,
    SkillRatingSuggestion,
    Service,
    ServiceSkillRequirementGroup,
    TimeSlot,
    WorkflowTask,
    BillingCode,
    Feedback,
    Client,
    ClientOnboarding,
    Contact,
    FrameworkAgreement,
    Qualification,
    QualificationSkill,
    QualificationRecord,
    AwardingBody,
    OrganisationalUnitRole,
    UserSkill,
    TimeSlotType,
    TimeSlotComment,
    Project
)
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import F, ExpressionWrapper, DurationField, Q
from datetime import timedelta
from guardian.admin import GuardedModelAdmin
from import_export.admin import ImportExportModelAdmin

###########################
## This part makes sure we have the default groups configured...


class PhasesInline(admin.StackedInline):
    model = Phase
    extra = 0
    min_num = 0


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    inlines = [PhasesInline]
    search_fields = ['id', 'title', "external_id"]
    list_filter = ["status", ]


admin.site.register(JobSupportTeamRole)
admin.site.register(SupportBudgetDraw)
admin.site.register(SupportProfile)


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 1


@admin.register(Team)
class TeamAdmin(GuardedModelAdmin):
    inlines = [TeamMemberInline]


class OrganisationalUnitMemberInline(admin.TabularInline):
    model = OrganisationalUnitMember
    extra = 1


class OrganisationalUnitSupportTemplateMemberInline(admin.TabularInline):
    model = OrganisationalUnitSupportTemplateMember
    extra = 0


@admin.register(OrganisationalUnit)
class OrganisationalUnitAdmin(GuardedModelAdmin):
    inlines = [
        OrganisationalUnitMemberInline,
        OrganisationalUnitSupportTemplateMemberInline,
    ]
    list_display = ("name", "is_deleted")
    list_filter = ("is_deleted",)

    def get_queryset(self, request):
        # Include soft-deleted units so admins can see/restore them.
        return self.model.all_objects.get_queryset()


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 1
class SkillCategoryResource(resources.ModelResource):
    class Meta:
        model = SkillCategory
        import_id_fields = ("name",)
        fields = ("id", "name", "description", "slug")
        export_order = fields
class SkillCategoryAdmin(ImportExportModelAdmin):
    resource_classes = [SkillCategoryResource]
    inlines = [SkillInline]
    search_fields = ("name",)
admin.site.register(SkillCategory, SkillCategoryAdmin)


admin.site.register(TimeSlotType)


class ServiceSkillRequirementGroupInline(admin.TabularInline):
    model = ServiceSkillRequirementGroup
    extra = 0
    filter_horizontal = ("skills",)


class ServiceResource(resources.ModelResource):
    """Round-trips services with skills/quals rendered as pipe-separated *names*
    (not raw IDs), so the import spreadsheets stay human-editable."""

    skillsRequired = fields.Field(
        column_name="skillsRequired",
        attribute="skillsRequired",
        widget=ManyToManyWidget(Skill, field="name", separator="|"),
    )
    skillsDesired = fields.Field(
        column_name="skillsDesired",
        attribute="skillsDesired",
        widget=ManyToManyWidget(Skill, field="name", separator="|"),
    )
    qualificationsRequired = fields.Field(
        column_name="qualificationsRequired",
        attribute="qualificationsRequired",
        widget=ManyToManyWidget(Qualification, field="name", separator="|"),
    )
    qualificationsDesired = fields.Field(
        column_name="qualificationsDesired",
        attribute="qualificationsDesired",
        widget=ManyToManyWidget(Qualification, field="name", separator="|"),
    )

    class Meta:
        model = Service
        import_id_fields = ("name",)
        fields = (
            "id",
            "name",
            "is_core",
            "skillsRequired",
            "skillsDesired",
            "qualificationsRequired",
            "qualificationsDesired",
            "slug",
        )
        export_order = fields


class ServiceAdmin(ImportExportModelAdmin):
    resource_classes = [ServiceResource]
    inlines = [ServiceSkillRequirementGroupInline]
    search_fields = ("name",)
admin.site.register(Service, ServiceAdmin)


class ServiceSkillRequirementGroupResource(resources.ModelResource):
    service = fields.Field(
        column_name="service",
        attribute="service",
        widget=ForeignKeyWidget(Service, field="name"),
    )
    skills = fields.Field(
        column_name="skills",
        attribute="skills",
        widget=ManyToManyWidget(Skill, field="name", separator="|"),
    )

    class Meta:
        model = ServiceSkillRequirementGroup
        import_id_fields = ("service", "name")
        fields = ("id", "service", "name", "skills")
        export_order = fields


@admin.register(ServiceSkillRequirementGroup)
class ServiceSkillRequirementGroupAdmin(ImportExportModelAdmin):
    resource_classes = [ServiceSkillRequirementGroupResource]
    list_display = ("service", "name")
    filter_horizontal = ("skills",)
    search_fields = ("name", "service__name")



class DurationListFilter(admin.SimpleListFilter):
    title = _('Duration')
    parameter_name = 'duration'

    def lookups(self, request, model_admin):
        return (
            ('short', _('Short (< 30 min)')),
            ('medium', _('Medium (30 min - 2 hours)')),
            ('half_day', _('Half Day (3.5 hours - 4.5 hours)')),
            ('working_day', _('Working Day (7.5 - 8.5 hours)')),
            ('long_day', _('Long Day (> 8.5 hours)')),
            ('multi_day', _('Very Long (> 24 hours)')),
            ('working_week', _('Over a Working Week (> 42.5 hours)')),
        )

    def queryset(self, request, queryset):
        # Create a duration expression
        queryset = queryset.annotate(
            duration=ExpressionWrapper(
                F('end') - F('start'),
                output_field=DurationField()
            )
        )
        
        if self.value() == 'short':
            return queryset.filter(duration__lt=timedelta(minutes=30))
        if self.value() == 'medium':
            return queryset.filter(
                duration__gte=timedelta(minutes=30),
                duration__lt=timedelta(hours=3.5)
            )
        if self.value() == 'half_day':
            return queryset.filter(
                duration__gte=timedelta(hours=3.5),
                duration__lt=timedelta(hours=4.5)
            )
        if self.value() == 'working_day':
            return queryset.filter(
                duration__gte=timedelta(hours=4.5),
                duration__lt=timedelta(hours=8.5)
            )
        if self.value() == 'long_day':
            return queryset.filter(
                duration__gte=timedelta(hours=8.5),
                duration__lte=timedelta(hours=24)
            )
        if self.value() == 'multi_day':
            return queryset.filter(
                duration__gt=timedelta(hours=24),
                duration__lt=timedelta(hours=42.5)
            )
        if self.value() == 'working_week':
            return queryset.filter(duration__gte=timedelta(hours=42.5))
        return queryset
    

@admin.register(TimeSlot)
class TimeSlotAdmin(SimpleHistoryAdmin):
    readonly_fields = ['phase', 'project', "updated"]
    # Display these fields in the list view
    list_display = ('id', 'start', 'end', 'duration_display', 'user', "slot_type", "phase", "project", "deliveryRole", "is_onsite")
    
    # Add filters in the right sidebar
    list_filter = ('start', 'end', "slot_type", DurationListFilter)
    
    # Fields that can be searched
    search_fields = ('user__username', 'user__email')
    
    # Add date-based navigation
    date_hierarchy = 'start'
    
    # Fields to display in the edit form, grouped into fieldsets
    fieldsets = (
        (None, {
            'fields': ('user',)
        }),
        ('Time Information', {
            'fields': ('start', 'end'),
            'description': 'Set the start and end times for this time slot.'
        }),
    )
    
    # Calculate and format the duration
    def duration_display(self, obj):
        if obj.start and obj.end:
            duration = obj.end - obj.start
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
        
            # Format the values before passing to format_html
            hours_str = f"{int(hours)}"
            minutes_str = f"{int(minutes)}"            
            
            # Format based on duration length
            if hours > 0:
                color = '#007bff' if duration.total_seconds() > 14400 else '#dc3545'  # Blue if > 4h, red if <= 4h
                return format_html(
                    '<span style="color: {}">{} h {} m</span>',
                    color, hours_str, minutes_str
                )
            else:
                return format_html(
                    '<span style="color: {}">{} m</span>',
                    '#28a745', minutes_str  # Green for short durations
                )
        return "-"
    
    # Set a descriptive name for the calculated field
    duration_display.short_description = "Duration"
    duration_display.admin_order_field = 'end'  # Allow sorting by end time as proxy
    
    # Optimize database queries
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('user')




admin.site.register(TimeSlotComment)
admin.site.register(WorkflowTask)
admin.site.register(BillingCode)


@admin.register(Feedback)
class FeedbackAdmin(SimpleHistoryAdmin):
    readonly_fields = ['phase', 'author']
    list_display = ["phase", "author", "created_on", "feedbackType"]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    search_fields = ['id', 'title', "external_id"]

admin.site.register(OrganisationalUnitRole)

#### Quals
class AwardingBodyResource(resources.ModelResource):
    class Meta:
        model = AwardingBody
        import_id_fields = ("name",)
        fields = ("id", "name", "description", "url", "slug")
        export_order = fields
class AwardingBodyAdmin(ImportExportModelAdmin):
    resource_classes = [AwardingBodyResource]
    search_fields = ("name",)
admin.site.register(AwardingBody, AwardingBodyAdmin)


class QualificationSkillInline(admin.TabularInline):
    model = QualificationSkill
    extra = 1
    autocomplete_fields = ("skill",)


class QualificationResource(resources.ModelResource):
    awarding_body = fields.Field(
        column_name="awarding_body",
        attribute="awarding_body",
        widget=ForeignKeyWidget(AwardingBody, field="name"),
    )

    class Meta:
        model = Qualification
        import_id_fields = ("name",)
        fields = (
            "id",
            "awarding_body",
            "name",
            "short_name",
            "description",
            "validity_period",
            "verification_required",
            "url",
            "guidance_url",
            "slug",
        )
        export_order = fields


class QualificationSkillResource(resources.ModelResource):
    """The qualification -> skill -> suggested-rating map (one row per link)."""

    qualification = fields.Field(
        column_name="qualification",
        attribute="qualification",
        widget=ForeignKeyWidget(Qualification, field="name"),
    )
    skill = fields.Field(
        column_name="skill",
        attribute="skill",
        widget=ForeignKeyWidget(Skill, field="name"),
    )

    class Meta:
        model = QualificationSkill
        import_id_fields = ("qualification", "skill")
        fields = ("id", "qualification", "skill", "suggested_rating")
        export_order = fields


class QualificationAdmin(ImportExportModelAdmin):
    resource_classes = [QualificationResource]
    inlines = [QualificationSkillInline]
    search_fields = ("name", "short_name")
    list_display = ("name", "short_name", "awarding_body")
admin.site.register(Qualification, QualificationAdmin)


@admin.register(QualificationSkill)
class QualificationSkillAdmin(ImportExportModelAdmin):
    resource_classes = [QualificationSkillResource]
    list_display = ("qualification", "skill", "suggested_rating")
    list_filter = ("suggested_rating",)
    search_fields = ("qualification__name", "skill__name")


class QualificationRecordResource(resources.ModelResource):
    class Meta:
        model = QualificationRecord
class QualificationRecordAdmin(ImportExportModelAdmin):
    resource_classes = [QualificationRecordResource]
admin.site.register(QualificationRecord, QualificationRecordAdmin)


#### Skill
class SkillResource(resources.ModelResource):
    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=ForeignKeyWidget(SkillCategory, field="name"),
    )

    class Meta:
        model = Skill
        import_id_fields = ("name",)
        fields = (
            "id",
            "category",
            "name",
            "description",
            "rating_desc_support",
            "rating_desc_independent",
            "rating_desc_specialist",
            "slug",
        )
        export_order = fields


class SkillAdmin(ImportExportModelAdmin):
    resource_classes = [SkillResource]
    search_fields = ("name",)
    list_display = ("name", "category", "has_rating_descriptors")
    list_filter = ("category",)


admin.site.register(Skill, SkillAdmin)


@admin.register(SkillRatingSuggestion)
class SkillRatingSuggestionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "skill",
        "suggested_rating",
        "source",
        "status",
        "created_on",
    )
    list_filter = ("status", "source", "suggested_rating")
    search_fields = ("user__email", "user__first_name", "user__last_name", "skill__name")
    autocomplete_fields = ("skill",)


#### Client
class ClientResource(resources.ModelResource):
    class Meta:
        model = Client


@admin.register(Client)
class ClientAdmin(ImportExportModelAdmin):
    resource_classes = [ClientResource]
    list_display = ("name", "is_deleted")
    list_filter = ("is_deleted",)

    def get_queryset(self, request):
        # Include soft-deleted clients so admins can see/restore them.
        return self.model.all_objects.get_queryset()


#### ClientOnboarding
class ClientOnboardingResource(resources.ModelResource):
    class Meta:
        model = ClientOnboarding

@admin.register(ClientOnboarding)
class ClientOnboardingAdmin(ImportExportModelAdmin):
    resource_classes = [ClientOnboardingResource]


#### FrameworkAgreement
class FrameworkAgreementResource(resources.ModelResource):
    class Meta:
        model = FrameworkAgreement

@admin.register(FrameworkAgreement)
class FrameworkAgreementAdmin(ImportExportModelAdmin):
    resource_classes = [FrameworkAgreementResource]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "company"]


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ["skill", "user", "rating", "last_updated_on"]
