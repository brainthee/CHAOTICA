from django.urls import reverse
from menu import Menu, MenuItem



Menu.add_item("main", MenuItem("Jobs",
                            reverse("job_list"),
                            icon="cubes",
                            check=lambda request: request.user.has_perm('jobtracker.view_job'),
                            weight=1,))

Menu.add_item("main", MenuItem("Scheduler",
                            reverse("view_scheduler"),
                            icon="calendar",
                            check=lambda request: request.user.has_perm('jobtracker.view_scheduler'),
                            weight=2,))
Menu.add_item("main", MenuItem("Clients",
                            reverse("client_list"),
                            icon="handshake",
                            check=lambda request: request.user.has_perm('jobtracker.view_client'),
                            weight=3,))


Menu.add_item("main", MenuItem("Reporting",
                            reverse("view_reports"),
                            weight=4,
                            check=lambda request: request.user.has_perm('jobtracker.view_report'),
                            icon="file-lines"))

ops_children = (
    MenuItem("Skills",
                reverse("skill_list"),
                icon="readme",
                check=lambda request: request.user.has_perm('jobtracker.view_skill'),
                icon_prefix="fab fa-",
                weight=1,
                ),
    MenuItem("Services",
                reverse("service_list"),
                check=lambda request: request.user.has_perm('jobtracker.view_service'),
                icon="laptop-code",
                weight=1,
                ),
    MenuItem("Workflow Checklists",
                reverse("wf_tasks_list"),
                check=lambda request: request.user.has_perm('jobtracker.view_workflowtask'),
                icon="list-check",
                weight=1,
                ),
    MenuItem("Manage Leave",
                reverse("manage_leave"),
                icon="person-walking-arrow-right",
                check=lambda request: request.user.has_perm('jobtracker.manage_leave'),
                weight=1,
                ),
    MenuItem("Organisational Units",
                reverse("organisationalunit_list"),
                check=lambda request: request.user.has_perm('jobtracker.view_organisationalunit'),
                icon="building",
                weight=10,),
)

Menu.add_item("main", MenuItem("Operations",
                               '#',
                               weight=10,
                               icon="gears",
                               children=ops_children))


