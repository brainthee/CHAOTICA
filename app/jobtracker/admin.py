from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Phase,
    Job,
    JobSupportTeamRole,
    OrganisationalUnit,
    OrganisationalUnitMember,
    Team, TeamMember,
    Skill,
    SkillCategory,
    Service,
    TimeSlot,
    WorkflowTask,
    BillingCode,
    Feedback,
    Client,
    ClientOnboarding,
    Contact,
    FrameworkAgreement,
    Qualification,
    QualificationRecord,
    AwardingBody,
    Accreditation,
    OrganisationalUnitRole,
    UserSkill,
    TimeSlotType,
    TimeSlotComment,
    Project
)
from import_export import resources
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


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 1


@admin.register(Team)
class TeamAdmin(GuardedModelAdmin):
    inlines = [TeamMemberInline]


class OrganisationalUnitMemberInline(admin.TabularInline):
    model = OrganisationalUnitMember
    extra = 1


@admin.register(OrganisationalUnit)
class OrganisationalUnitAdmin(GuardedModelAdmin):
    inlines = [OrganisationalUnitMemberInline]


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 1
class SkillCategoryResource(resources.ModelResource):
    class Meta:
        model = SkillCategory
class SkillCategoryAdmin(ImportExportModelAdmin):
    resource_classes = [SkillCategoryResource]
    inlines = [SkillInline]
admin.site.register(SkillCategory, SkillCategoryAdmin)


admin.site.register(TimeSlotType)


class ServiceResource(resources.ModelResource):
    class Meta:
        model = Service
class ServiceAdmin(ImportExportModelAdmin):
    resource_classes = [ServiceResource]
admin.site.register(Service, ServiceAdmin)


@admin.register(TimeSlot)
class TimeSlotAdmin(SimpleHistoryAdmin):
    readonly_fields = ['phase', 'project', "updated"]


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
class AwardingBodyAdmin(ImportExportModelAdmin):
    resource_classes = [AwardingBodyResource]
admin.site.register(AwardingBody, AwardingBodyAdmin)

class QualificationResource(resources.ModelResource):
    class Meta:
        model = Qualification
class QualificationAdmin(ImportExportModelAdmin):
    resource_classes = [QualificationResource]
admin.site.register(Qualification)

class QualificationRecordResource(resources.ModelResource):
    class Meta:
        model = QualificationRecord
class QualificationRecordAdmin(ImportExportModelAdmin):
    resource_classes = [QualificationRecordResource]
admin.site.register(QualificationRecord)

class AccreditationResource(resources.ModelResource):
    class Meta:
        model = Accreditation
class AccreditationAdmin(ImportExportModelAdmin):
    resource_classes = [AccreditationResource]
admin.site.register(Accreditation)


#### Skill
class SkillResource(resources.ModelResource):
    class Meta:
        model = Skill


class SkillAdmin(ImportExportModelAdmin):
    resource_classes = [SkillResource]


admin.site.register(Skill, SkillAdmin)


#### Client
class ClientResource(resources.ModelResource):
    class Meta:
        model = Client


@admin.register(Client)
class ClientAdmin(ImportExportModelAdmin):
    resource_classes = [ClientResource]


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
