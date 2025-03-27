from django.urls import reverse
from menu import Menu, MenuItem
from chaotica_utils.utils import PermMenuItem, RoleMenuItem


Menu.add_item(
    "add",
    RoleMenuItem(
        "Add Job",
        reverse("job_create"),
        check=lambda request: request.user.is_authenticated,
        icon="cubes",
        requiredRole="*",  # Any role will do!
        weight=1,
    ),
)


Menu.add_item(
    "user",
    MenuItem(
        "My Qualifications",
        reverse("view_own_qualifications"),
        check=lambda request: request.user.is_authenticated,
        icon="certificate",
        weight=1,
    ),
)


Menu.add_item(
    "main",
    RoleMenuItem(
        "Jobs",
        reverse("job_list"),
        check=lambda request: request.user.is_authenticated,
        icon="cubes",
        requiredRole="*",  # Any role will do!
        weight=1,
    ),
)

Menu.add_item(
    "main",
    MenuItem(
        "Scheduler",
        reverse("view_scheduler"),
        check=lambda request: request.user.is_authenticated,
        icon="calendar",
        # perm='jobtracker.view_scheduler',
        weight=2,
    ),
)

Menu.add_item(
    "main",
    PermMenuItem(
        "Clients",
        reverse("client_list"),
        check=lambda request: request.user.is_authenticated,
        icon="handshake",
        perm="jobtracker.view_client",
        weight=3,
    ),
)

Menu.add_item(
    "main",
    MenuItem(
        "Reporting",
        reverse("view_reports"),
        check=lambda request: request.user.is_authenticated,
        weight=4,
        # perm='jobtracker.view_report',
        icon="file-lines",
    ),
)

Menu.add_item(
    "ops",
    PermMenuItem(
        "Teams",
        reverse("team_list"),
        check=lambda request: request.user.is_authenticated,
        icon="people-group",
        perm="jobtracker.view_team",
        weight=1,
    ),
)

Menu.add_item(
    "ops",
    PermMenuItem(
        "Skills",
        reverse("skill_list"),
        check=lambda request: request.user.is_authenticated,
        icon="readme",
        perm="jobtracker.view_skill",
        icon_prefix="fab fa-",
        weight=1,
    ),
)
Menu.add_item(
    "ops",
    PermMenuItem(
        "Services",
        reverse("service_list"),
        check=lambda request: request.user.is_authenticated,
        perm="jobtracker.view_service",
        icon="laptop-code",
        weight=1,
    ),
)
Menu.add_item(
    "ops",
    PermMenuItem(
        "Qualifications",
        reverse("qualification_list"),
        check=lambda request: request.user.is_authenticated,
        perm="jobtracker.view_qualification",
        icon="certificate",
        weight=1,
    ),
)
Menu.add_item(
    "ops",
    PermMenuItem(
        "Projects",
        reverse("project_list"),
        check=lambda request: request.user.is_authenticated,
        perm="jobtracker.view_projects",
        icon="diagram-project",
        weight=3,
    ),
)
Menu.add_item(
    "ops",
    PermMenuItem(
        "Accreditation",
        reverse("qualification_list"),
        check=lambda request: request.user.is_authenticated,
        perm="jobtracker.view_qualification",
        icon="certificate",
        weight=1,
    ),
)
Menu.add_item(
    "ops",
    PermMenuItem(
        "Workflow Checklists",
        reverse("wf_tasks_list"),
        check=lambda request: request.user.is_authenticated,
        perm="jobtracker.view_workflowtask",
        icon="list-check",
        weight=5,
    ),
)
Menu.add_item(
    "ops",
    MenuItem(
        "Manage Leave",
        reverse("manage_leave"),
        check=lambda request: request.user.is_authenticated,
        icon="person-walking-arrow-right",
        weight=6,
    ),
)
Menu.add_item(
    "ops",
    PermMenuItem(
        "Billing Codes",
        reverse("billingcode_list"),
        check=lambda request: request.user.is_authenticated,
        perm="jobtracker.view_billingcode",
        icon="receipt",
        weight=5,
    ),
)
Menu.add_item(
    "ops",
    PermMenuItem(
        "Organisational Units",
        reverse("organisationalunit_list"),
        check=lambda request: request.user.is_authenticated,
        perm="jobtracker.view_organisationalunit",
        icon="building",
        weight=10,
    ),
)
