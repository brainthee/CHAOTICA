from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from guardian.admin import GuardedModelAdmin
from .models import (
    User,
    UserCost,
    UserInvitation,
    Notification,
    Group,
    Language,
    LeaveRequest,
    HolidayCountry,
    Holiday,
)


class CustomUserAdmin(GuardedModelAdmin):
    list_display = ["email", "first_name", "last_name", "is_active"]
    fieldsets = (
        # *UserAdmin.fieldsets,  # original form fieldsets, expanded
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
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
                ),
            },
        ),
    )


admin.site.register(User, CustomUserAdmin)


@admin.register(UserCost)
class UserCostAdmin(admin.ModelAdmin):
    list_display = ["user", "effective_from", "cost_per_hour"]


@admin.register(UserInvitation)
class UserCostAdmin(admin.ModelAdmin):
    list_display = ["invited_email", "sent", "accepted", "invited_by"]


@admin.register(Notification)
class UserCostAdmin(admin.ModelAdmin):
    list_display = ["user", "timestamp", "title"]


admin.site.register(Group, GroupAdmin)
admin.site.register(Language)
admin.site.register(LeaveRequest)
admin.site.register(HolidayCountry)


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ["country", "date", "reason"]
    list_filter = ["country"]
