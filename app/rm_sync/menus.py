from django.urls import reverse
from menu import Menu, MenuItem
from chaotica_utils.utils import RoleMenuItem, PermMenuItem


# Admin menu
Menu.add_item(
    "admin",
    PermMenuItem(
        "Manage RM Sync",
        reverse("rm_settings"),
        icon="list-check",
        perm="chaotica_utils.manage_site_settings",
        weight=20,
    ),
)