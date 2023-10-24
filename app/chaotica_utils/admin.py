from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from guardian.admin import GuardedModelAdmin
from .models import User, UserCost, UserInvitation, Notification, Group, Language, LeaveRequest, HolidayCountry, Holiday

class CustomUserAdmin(GuardedModelAdmin):
    fieldsets = (
        *UserAdmin.fieldsets,  # original form fieldsets, expanded
        (                      # new fieldset added on to the bottom
            'Extra Fields',  # group heading of your choice; set to None for a blank space instead of a header
            {
                'fields': (
                    'manager',
                    'acting_manager',
                    'profile_image',
                    'location',
                    'phone_number',
                    'languages',
                    'job_title',
                    'site_theme',
                    'show_help',
                    'schedule_feed_id',
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
admin.site.register(Holiday)