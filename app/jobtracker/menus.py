from django.urls import reverse
from menu import Menu, MenuItem
from chaotica_utils.utils import PermMenuItem, RoleMenuItem


Menu.add_item("main", RoleMenuItem("Jobs",
                            reverse("job_list"),
                            icon="cubes",
                            requiredRole='*', # Any role will do!
                            weight=1,))

Menu.add_item("main", PermMenuItem("Scheduler",
                            reverse("view_scheduler"),
                            icon="calendar",
                            perm='jobtracker.view_scheduler',
                            weight=2,))

Menu.add_item("main", PermMenuItem("Clients",
                            reverse("client_list"),
                            icon="handshake",
                            perm='jobtracker.view_client',
                            weight=3,))

Menu.add_item("main", PermMenuItem("Reporting",
                            reverse("view_reports"),
                            weight=4,
                            perm='jobtracker.view_report',
                            icon="file-lines"))

ops_children = (
    PermMenuItem("Skills",
                reverse("skill_list"),
                icon="readme",
                perm='jobtracker.view_skill',
                icon_prefix="fab fa-",
                weight=1,
                ),
    PermMenuItem("Services",
                reverse("service_list"),
                perm='jobtracker.view_service',
                icon="laptop-code",
                weight=1,
                ),
    PermMenuItem("Certifications",
                reverse("certification_list"),
                perm='jobtracker.view_certification',
                icon="certificate",
                weight=1,
                ),
    PermMenuItem("Workflow Checklists",
                reverse("wf_tasks_list"),
                perm='jobtracker.view_workflowtask',
                icon="list-check",
                weight=1,
                ),
    PermMenuItem("Manage Leave",
                reverse("manage_leave"),
                icon="person-walking-arrow-right",
                perm='jobtracker.manage_leave',
                weight=1,
                ),
    PermMenuItem("Organisational Units",
                reverse("organisationalunit_list"),
                perm='jobtracker.view_organisationalunit',
                icon="building",
                weight=10,),
)

Menu.add_item("main", MenuItem("Operations",
                               '#',
                               weight=10,
                               icon="gears",
                               children=ops_children))


