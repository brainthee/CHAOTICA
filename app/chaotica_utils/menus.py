from django.urls import reverse
from menu import Menu, MenuItem
from .enums import GlobalRoles
from .utils import RoleMenuItem


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
    MenuItem("Run Background Tasks",
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
