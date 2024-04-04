from django.urls import reverse
from menu import Menu, MenuItem

Menu.add_item(
    "main",
    MenuItem(
        "Dashboard",
        reverse("home"),
        icon="info",
        weight=0,
    ),
)
