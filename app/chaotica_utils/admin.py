from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from guardian.admin import GuardedModelAdmin
from .models import (
    User,
    UserCost,
    UserInvitation,
    Group,
    Language,
    LeaveRequest,
    Holiday,
    Note,
)

class CustomUserAdmin(GuardedModelAdmin):
    list_display = ["email", "first_name", "last_name", "is_active"]
    search_fields = ['email', 'first_name', 'last_name']
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
                    "country",
                    "phone_number",
                    "languages",
                    "job_title",
                    "site_theme",
                    "show_help",
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
