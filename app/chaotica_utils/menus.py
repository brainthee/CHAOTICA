from django.urls import reverse
from menu import Menu, MenuItem
from .enums import GlobalRoles
from .utils import RoleMenuItem, PermMenuItem


Menu.add_item(
    "user",
    MenuItem(
        "Profile",
        reverse("view_own_profile"),
        icon="user",
        weight=1,
    ),
)

Menu.add_item(
    "user",
    MenuItem(
        "Manage Annual Leave",
        reverse("view_own_leave"),
        icon="person-walking-arrow-right",
        weight=1,
    ),
)

# Admin menu
Menu.add_item(
    "admin",
    PermMenuItem(
        "Users",
        reverse("user_list"),
        icon="user-group",
        perm="chaotica_utils.manage_user",
        weight=10,
    )
)
Menu.add_item(
    "admin",
    PermMenuItem(
        "Activity Log",
        reverse("view_activity"),
        icon="magnifying-glass",
        perm="chaotica_utils.view_activity_logs",
        weight=70,
    ),
)
Menu.add_item(
    "admin",
    MenuItem(
        "SQL Explorer",
        reverse("explorer_index"),
        icon="database",
        check=lambda request: request.user.is_superuser,
        weight=70,
    ),
)
Menu.add_item(
    "admin",
    PermMenuItem(
        "Run Background Tasks",
        reverse("run_tasks"),
        icon="list-check",
        perm="chaotica_utils.manage_site_settings",
        weight=80,
    ),
)
Menu.add_item(
    "admin",
    PermMenuItem(
        "Send Test Notification",
        reverse("test_notification"),
        icon="envelope-open-text",
        perm="chaotica_utils.manage_site_settings",
        weight=80,
    ),
)
Menu.add_item(
    "admin",
    PermMenuItem(
        "Settings",
        reverse("app_settings"),
        icon="sliders",
        perm="chaotica_utils.manage_site_settings",
        weight=99,
    ),
)
Menu.add_item(
    "admin",
    MenuItem(
        "Django Admin",
        reverse("admin:index"),
        icon="wrench",
        check=lambda request: request.user.is_superuser,
        weight=100,
    )
)