from django.urls import reverse
from menu import Menu, MenuItem
from .enums import GlobalRoles
from django.conf import settings


class RoleMenuItem(MenuItem):
    """Custom MenuItem that checks permissions based on the view associated
    with a URL"""
    def check(self, request):
        if self.requiredRole:
             self.visible = request.user.groups.filter(
                 name=settings.GLOBAL_GROUP_PREFIX+GlobalRoles.CHOICES[self.requiredRole][1]).exists()
        else:
            self.visible = False

Menu.add_item("user", MenuItem("Profile",
                               reverse('view_own_profile'),
                               icon="user",
                               weight=1,))

Menu.add_item("user", MenuItem("Manage Annual Leave",
                               reverse('view_own_leave'),
                               icon="person-walking-arrow-right",
                               weight=1,))

admin_children = (
    MenuItem("Users",
        reverse("user_list"),
        icon="user-group",
        weight=10,),
    MenuItem("Settings",
        reverse("app_settings"),
        icon="sliders",
        weight=10,),
    MenuItem("Django Admin",
        reverse("admin:index"),
        icon="wrench",
        weight=10,),
    MenuItem("Run Tasks",
        reverse("run_tasks"),
        check=lambda request: request.user.is_superuser,
        icon="list-check",
        weight=10,),
    MenuItem("Test Notification",
        reverse("test_notification"),
        check=lambda request: request.user.is_superuser,
        icon="envelope-open-text",
        weight=10,),
)

Menu.add_item("main", RoleMenuItem("Administration",
                        reverse("job_list"),
                        weight=20,
                        icon="toolbox",
                        children=admin_children,
                        requiredRole=GlobalRoles.ADMIN,))
