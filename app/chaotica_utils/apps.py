from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.db import connections
from .enums import *
from django.conf import settings


def table_exists(table_name: str) -> bool:
    return table_name in connections["default"].introspection.table_names()


def populate_groups():
    from .models import Group
    from django.contrib.auth.models import Permission
    from guardian.shortcuts import assign_perm
    from constance import config

    if table_exists("auth_permission") and Permission.objects.filter(codename="view_client").exists():
        # create default groups
        for globalRole in GlobalRoles.CHOICES:
            group, created = Group.objects.get_or_create(name=settings.GLOBAL_GROUP_PREFIX+globalRole[1])
            group.permissions.clear()
            for perm in GlobalRoles.PERMISSIONS[globalRole[0]][1]: # how ugly!
                try:
                    assign_perm(perm, group, None)
                except Permission.DoesNotExist:
                    pass # ignore this for the moment!
    

class ChaoticaUtilsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chaotica_utils"

    def ready(self):
        populate_groups()