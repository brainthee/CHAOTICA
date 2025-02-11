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

Menu.add_item(
    "user",
    MenuItem(
        "Onboarded Clients",
        reverse("view_own_onboarding"),
        icon="person-snowboarding",
        weight=2,
    ),
)

Menu.add_item(
    "ops",
    PermMenuItem(
        "Manage Holidays",
        reverse("holiday_list"),
        icon="user-group",
        perm="chaotica_utils.manage_holidays",
        weight=8,
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
    ),
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
    ),
)

admin_tasks = (
    MenuItem(
        "Update ALL phase dates",
        reverse("admin_task_update_phase_dates"),
        weight=10,
        icon="calendar",
    ),
    MenuItem(
        "Sync Global Permissions",
        reverse("admin_task_sync_global_permissions"),
        weight=10,
        icon="rotate",
    ),
    MenuItem(
        "Sync Role Permissions to Default",
        reverse("admin_task_sync_role_permissions_to_default"),
        weight=10,
        icon="id-card",
    ),
    MenuItem(
        "Sync Role Permissions",
        reverse("admin_task_sync_role_permissions"),
        weight=10,
        icon="rotate",
    ),
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
    MenuItem(
        "Admin Tasks",
        reverse("admin:index"),
        icon="list-check",
        children=admin_tasks,
        check=lambda request: request.user.is_superuser,
        weight=100,
    ),
)
