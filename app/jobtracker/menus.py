from django.urls import reverse
from menu import Menu, MenuItem



Menu.add_item("main", MenuItem("Jobs",
                                reverse("job_list"),
                                icon="swatchbook",
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

rept_children = (
    MenuItem("Statistics",
            reverse("view_stats"),
            icon="comment",
             weight=10,),
    MenuItem("Reports",
            reverse("view_stats"),
            icon="comment",
             weight=10,),
)

Menu.add_item("main", MenuItem("Analysis",
                               reverse("job_list"),
                               weight=4,
                               children=rept_children))

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
    MenuItem("Manage Leave",
                reverse("manage_leave"),
                icon="laptop-code",
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
                               children=ops_children))


