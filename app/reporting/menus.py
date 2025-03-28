from django.urls import reverse
from menu import Menu, MenuItem

Menu.add_item(
    "main",
    MenuItem(
        "Reporting",
        reverse("reporting:index"),
        weight=4,
        # perm='jobtracker.view_report',
        icon="file-lines",
    ),
)