from django.urls import reverse
from menu import Menu, MenuItem
from .enums import GlobalRoles
from .utils import RoleMenuItem, PermMenuItem


Menu.add_item(
    "user",
    MenuItem(
        "View Profile",
        reverse("view_own_profile"),
        icon="user",
        check=lambda request: request.user.is_authenticated,
        weight=1,
    ),
)

Menu.add_item(
    "user",
    MenuItem(
        "Edit Profile",
        lambda request: request.user.get_edit_url(),
        check=lambda request: request.user.is_authenticated,
        icon="user",
        weight=1,
    ),
)

Menu.add_item(
    "user",
    MenuItem(
        "Manage Annual Leave",
        reverse("view_own_leave"),
        check=lambda request: request.user.is_authenticated,
        icon="person-walking-arrow-right",
        weight=1,
    ),
)

Menu.add_item(
    "user",
    MenuItem(
        "Onboarded Clients",
        lambda request: reverse("view_onboarding", kwargs={"email": request.user}),
        check=lambda request: request.user.is_authenticated,
        icon="person-snowboarding",
        weight=2,
    ),
)

Menu.add_item(
    "ops",
    PermMenuItem(
        "Manage Holidays",
        reverse("holiday_list"),
        check=lambda request: request.user.is_authenticated,
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
        check=lambda request: request.user.is_authenticated,
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
        check=lambda request: request.user.is_authenticated,
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
        check=lambda request: request.user.is_authenticated,
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
        check=lambda request: request.user.is_authenticated,
        weight=10,
        icon="calendar",
    ),
    MenuItem(
        "Sync Global Permissions",
        reverse("admin_task_sync_global_permissions"),
        check=lambda request: request.user.is_authenticated,
        weight=10,
        icon="rotate",
    ),
    MenuItem(
        "Sync Role Permissions to Default",
        reverse("admin_task_sync_role_permissions_to_default"),
        check=lambda request: request.user.is_authenticated,
        weight=10,
        icon="id-card",
    ),
    MenuItem(
        "Sync Role Permissions",
        reverse("admin_task_sync_role_permissions"),
        check=lambda request: request.user.is_authenticated,
        weight=10,
        icon="rotate",
    ),
    MenuItem(
        "Send Test Notification",
        reverse("admin_send_test_notification"),
        check=lambda request: request.user.is_authenticated,
        icon="envelope-open-text",
        weight=10,
    ),
    MenuItem(
        "Trigger Error",
        reverse("admin_trigger_error"),
        check=lambda request: request.user.is_authenticated,
        icon="bug",
        weight=10,
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
