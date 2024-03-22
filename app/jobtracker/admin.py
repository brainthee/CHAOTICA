from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Phase, Job, JobSupportTeamRole, OrganisationalUnit, OrganisationalUnitMember, Skill, \
    SkillCategory, Service, TimeSlot, WorkflowTask, BillingCode, \
    Feedback, Client, Contact, FrameworkAgreement, \
    Qualification, QualificationRecord, QualificationTag, AwardingBody, \
    Accreditation, OrganisationalUnitRole, \
    UserSkill, TimeSlotType
from import_export import resources
from guardian.admin import GuardedModelAdmin
from import_export.admin import ImportExportModelAdmin

###########################
## This part makes sure we have the default groups configured...

class PhasesInline(admin.StackedInline):
    model = Phase
    extra = 1
    min_num = 0

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    inlines = [PhasesInline]


admin.site.register(JobSupportTeamRole)


class OrganisationalUnitMemberInline(admin.TabularInline):
    model = OrganisationalUnitMember
    extra = 1

@admin.register(OrganisationalUnit)
class OrganisationalUnitAdmin(GuardedModelAdmin):
    inlines = [OrganisationalUnitMemberInline]


class SkillInline(admin.TabularInline):
    model = Skill
    extra = 1

@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    inlines = [SkillInline]

admin.site.register(TimeSlotType)
admin.site.register(Service)
admin.site.register(TimeSlot, SimpleHistoryAdmin)
admin.site.register(WorkflowTask)
admin.site.register(BillingCode)
admin.site.register(Feedback)
admin.site.register(OrganisationalUnitRole)

admin.site.register(AwardingBody)
admin.site.register(Qualification)
admin.site.register(QualificationRecord)
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
        
class ClientAdmin(ImportExportModelAdmin):
    resource_classes = [ClientResource]

admin.site.register(Client, ClientAdmin)

#### FrameworkAgreement
class FrameworkAgreementResource(resources.ModelResource):
    class Meta:
        model = FrameworkAgreement

class FrameworkAgreementAdmin(ImportExportModelAdmin):
    resource_classes = [FrameworkAgreementResource]

admin.site.register(FrameworkAgreement, FrameworkAgreementAdmin)



@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "company"]



@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ["skill", "user", "rating", "last_updated_on"]
