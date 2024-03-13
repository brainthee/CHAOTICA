from django.urls import reverse
from menu import Menu, MenuItem
from .enums import GlobalRoles
from .utils import RoleMenuItem, PermMenuItem


Menu.add_item("user", MenuItem("Profile",
                               reverse('view_own_profile'),
                               icon="user",
                               weight=1,))

Menu.add_item("user", MenuItem("Manage Annual Leave",
                               reverse('view_own_leave'),
                               icon="person-walking-arrow-right",
                               weight=1,))

admin_children = (
    PermMenuItem("Users",
        reverse("user_list"),
        icon="user-group",
        perm="chaotica_utils.manage_user",
        weight=10,),
    PermMenuItem("Settings",
        reverse("app_settings"),
        icon="sliders",
        perm="chaotica_utils.manage_site_settings",
        weight=10,),
    PermMenuItem("Run Background Tasks",
        reverse("run_tasks"),
        icon="list-check",
        perm="chaotica_utils.manage_site_settings",
        weight=10,),
    PermMenuItem("Send Test Notification",
        reverse("test_notification"),
        icon="envelope-open-text",
        perm="chaotica_utils.manage_site_settings",
        weight=10,),
    MenuItem("Django Admin",
        reverse("admin:index"),
        icon="wrench",
        check=lambda request: request.user.is_superuser,
        weight=10,),
)

Menu.add_item("main", RoleMenuItem("Administration",
                        reverse("job_list"),
                        weight=20,
                        icon="toolbox",
                        children=admin_children,
                        requiredRole=GlobalRoles.ADMIN,))
