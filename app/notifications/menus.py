from django.urls import reverse
from menu import Menu, MenuItem

Menu.add_item(
    "user",
    MenuItem(
        "Notification Settings",
        reverse("notification_settings"),
        icon="user",
        weight=1,
    ),
)