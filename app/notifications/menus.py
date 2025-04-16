from django.urls import reverse
from menu import Menu, MenuItem
from chaotica_utils.utils import PermMenuItem

Menu.add_item(
    "user",
    MenuItem(
        "Notification Settings",
        reverse("notification_settings"),
        icon="user",
        weight=1,
    ),
)

Menu.add_item(
    "admin",
    MenuItem(
        "Notification Subscription Rules",
        reverse("notification_rules"),
        check=lambda request: request.user.is_superuser,
        icon="people-group",
        # perm="jobtracker.view_team",
        weight=1,
    ),
)