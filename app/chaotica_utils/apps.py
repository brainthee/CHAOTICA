from django.apps import AppConfig
from django.db import connections
from .enums import GlobalRoles
from django.conf import settings


def table_exists(table_name: str) -> bool:
    return table_name in connections["default"].introspection.table_names()


def populate_groups():
    from .models import Group
    from django.contrib.auth.models import Permission

    if table_exists("auth_permission") and \
        Permission.objects.filter(codename="view_client").exists(): # check DB is intact
        # create default groups
        for global_role in GlobalRoles.CHOICES:
            group, created = Group.objects.get_or_create(name=settings.GLOBAL_GROUP_PREFIX+global_role[1])
            # Only run this on startup if the group doesn't exist
            if created:
                group.sync_global_permissions()
    

class ChaoticaUtilsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chaotica_utils"

    def ready(self):
        populate_groups()