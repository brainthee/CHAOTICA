from django.urls import reverse
from menu import Menu, MenuItem
# from django.core.urlresolvers import resolve
from .enums import *
from django.conf import settings
from pprint import pprint


class RoleMenuItem(MenuItem):
    """Custom MenuItem that checks permissions based on the view associated
    with a URL"""
    def check(self, request):
        if self.requiredRole:
             self.visible = request.user.groups.filter(
                 name=settings.GLOBAL_GROUP_PREFIX+GlobalRoles.CHOICES[self.requiredRole][1]).exists()
        else:
            self.visible = False

# Example to use above
# RoleMenuItem("Roles",
#         reverse("view_scheduler"),
#         icon="edit_calendar",
#         weight=10,
#         requiredRole=GlobalRoles.SALES_MGR,),

Menu.add_item("user", MenuItem("Profile",
                               reverse('view_own_profile'),
                               icon="user",
                               weight=1,))

Menu.add_item("user", MenuItem("Manage Annual Leave",
                               reverse('view_own_leave'),
                               icon="user",
                               weight=1,))

# Menu.add_item("user", MenuItem("Help",
#                                reverse('help'),
#                                icon="help-circle",
#                                weight=1,))

admin_children = (
    MenuItem("Users",
        reverse("user_list"),
        icon="work_history",
        weight=10,),
    MenuItem("Settings",
        reverse("app_settings"),
        icon="settings",
        weight=10,),
    MenuItem("Django Admin",
        reverse("admin:index"),
        icon="settings",
        weight=10,),
    MenuItem("Run Tasks",
        reverse("run_tasks"),
        check=lambda request: request.user.is_superuser,
        icon="menu_book",
        weight=10,),
    MenuItem("Test Notification",
        reverse("test_notification"),
        check=lambda request: request.user.is_superuser,
        icon="menu_book",
        weight=10,),
)

Menu.add_item("main", RoleMenuItem("Administration",
                        reverse("job_list"),
                        weight=20,
                        children=admin_children,
                        requiredRole=GlobalRoles.ADMIN,))
