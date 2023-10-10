from django.urls import reverse
from menu import Menu, MenuItem



Menu.add_item("main", MenuItem("Jobs",
                                reverse("job_list"),
                                icon="cubes",
                                weight=1,
                                ))

Menu.add_item("main", MenuItem("Scheduler",
                                reverse("view_scheduler"),
                                icon="calendar",
                                weight=2,
                                ))
Menu.add_item("main", MenuItem("Clients",
                                reverse("client_list"),
                                icon="handshake",
                                weight=3,
                                ))


Menu.add_item("main", MenuItem("Reporting",
                               reverse("view_reports"),
                               weight=4,
                               icon="file-lines"))

ops_children = (
    MenuItem("Skills",
                reverse("skill_list"),
                icon="readme",
                icon_prefix="fab fa-",
                weight=1,
                ),
    MenuItem("Services",
                reverse("service_list"),
                icon="laptop-code",
                weight=1,
                ),
    MenuItem("Workflow Checklists",
                reverse("wf_tasks_list"),
                icon="list-check",
                weight=1,
                ),
    MenuItem("Manage Leave",
                reverse("manage_leave"),
                icon="person-walking-arrow-right",
                weight=1,
                ),
    MenuItem("Organisational Units",
                reverse("organisationalunit_list"),
                icon="building",
                weight=10,),
)

Menu.add_item("main", MenuItem("Operations",
                               reverse("job_list"),
                               weight=10,
                               icon="gears",
                               children=ops_children))


