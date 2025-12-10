from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from guardian.admin import GuardedModelAdmin
from .models import (
    Quote,
    User,
    UserCost,
    UserInvitation,
    Group,
    Language,
    LeaveRequest,
    Holiday,
    Note,
    HealthCheckAPIKey,
    JobLevel,
    UserJobLevel,
    IPTag,
    IPCIDRRange,
)


class UserJobLevelInline(admin.TabularInline):
    model = UserJobLevel
    extra = 0
    readonly_fields = ["created_at"]
    fields = ["job_level", "assigned_date", "is_current", "notes", "created_at"]


class CustomUserAdmin(GuardedModelAdmin):
    list_display = ["email", "first_name", "last_name", "is_active"]
    search_fields = ['email', 'first_name', 'last_name']
    inlines = [UserJobLevelInline]
    fieldsets = (
        # *UserAdmin.fieldsets,  # original form fieldsets, expanded
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "notification_email",
                    "first_name",
                    "last_name",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "date_joined",
                    "last_login",
                    "profile_last_updated",
                    "groups",
                ),
            },
        ),
        (  # new fieldset added on to the bottom
            "Extra Fields",  # group heading of your choice; set to None for a blank space instead of a header
            {
                "fields": (
                    "manager",
                    "acting_manager",
                    "profile_image",
                    "location",
                    "longitude",
                    "latitude",
                    "country",
                    "pref_timezone",
                    "phone_number",
                    "languages",
                    "job_title",
                    "site_theme",
                    "show_help",
                    "contracted_leave",
                    "carry_over_leave",
                    "contracted_leave_renewal",
                    "schedule_feed_id",
                    "external_id",
                ),
            },
        ),
    )


admin.site.register(User, CustomUserAdmin)


@admin.register(UserCost)
class UserCostAdmin(admin.ModelAdmin):
    list_display = ["user", "effective_from", "cost_per_hour"]


@admin.register(UserInvitation)
class UserInvitationAdmin(admin.ModelAdmin):
    list_display = ["invited_email", "sent", "accepted", "invited_by"]

admin.site.register(Group, GroupAdmin)
admin.site.register(Language)
admin.site.register(Note)
admin.site.register(Quote)

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    readonly_fields = ['user', 'timeslot']
    list_display = ["user", 
                    "requested_on", 
                    "start_date",
                    "end_date", 
                    "type_of_leave",
                    "timeslot", 
                    "authorised",
                    "cancelled",
                    "declined",
                    ]
    list_filter = [
        "type_of_leave",
        "start_date",
        "authorised",
        "cancelled",
        "declined",
    ]


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ["date", "country", "reason"]
    list_filter = ["country"]


@admin.register(HealthCheckAPIKey)
class HealthCheckAPIKeyAdmin(admin.ModelAdmin):
    list_display = ["user", "key", "created_at", "last_used", "is_active"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "key"]
    readonly_fields = ["key", "created_at", "last_used"]

    def has_add_permission(self, request):
        # Prevent manual creation - keys should be created through the app
        return False


@admin.register(JobLevel)
class JobLevelAdmin(admin.ModelAdmin):
    list_display = ["short_label", "long_label", "order", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["short_label", "long_label"]
    ordering = ["order"]

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return ["created_at", "updated_at"]
        return ["created_at", "updated_at"]


@admin.register(UserJobLevel)
class UserJobLevelAdmin(admin.ModelAdmin):
    list_display = ["user", "job_level", "assigned_date", "is_current"]
    list_filter = ["is_current", "assigned_date", "job_level"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "job_level__short_label"]
    readonly_fields = ["created_at"]
    date_hierarchy = "assigned_date"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'job_level')


class IPCIDRRangeInline(admin.TabularInline):
    model = IPCIDRRange
    extra = 0
    fields = ["cidr", "description", "is_active"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(IPTag)
class IPTagAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "color", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [IPCIDRRangeInline]

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return ["created_at", "updated_at"]
        return ["created_at", "updated_at"]


@admin.register(IPCIDRRange)
class IPCIDRRangeAdmin(admin.ModelAdmin):
    list_display = ["tag", "cidr", "description", "is_active", "created_at"]
    list_filter = ["is_active", "created_at", "tag"]
    search_fields = ["tag__name", "cidr", "description"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["tag"]

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return ["created_at", "updated_at"]
        return ["created_at", "updated_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tag')
