from django.apps import AppConfig
from django.db import connections


def table_exists(table_name: str) -> bool:
    return table_name in connections["default"].introspection.table_names()


def populate_timeslot_types():
    from .models import TimeSlotType
    from .enums import DefaultTimeSlotTypes

    if table_exists("jobtracker_timeslottype"):
        if not TimeSlotType.objects.all().count(): # Don't run if we already have types in the DB
            for default_type in DefaultTimeSlotTypes.DEFAULTS:
                instance, created = TimeSlotType.objects.get_or_create(
                    pk=default_type['pk'], defaults=default_type)
                if created:
                    for attr, value in default_type.items(): 
                        setattr(instance, attr, value)
                    instance.save()


def populate_default_unit_roles():
    from .models import OrganisationalUnitRole
    from chaotica_utils.enums import UnitRoles
    from django.contrib.auth.models import Permission

    if table_exists("jobtracker_organisationalunitrole"):
        if not OrganisationalUnitRole.objects.all().count(): # Don't run if we already have roles in the DB
            for role in UnitRoles.DEFAULTS:
                instance, created = OrganisationalUnitRole.objects.get_or_create(
                    pk=role['pk'], name=role['name'])
                if created:
                    for attr, value in role.items(): 
                        setattr(instance, attr, value)

                    for perm in UnitRoles.PERMISSIONS[role['pk']][1]:
                        permission = Permission.objects.get(codename=perm.split(".")[1])
                        instance.permissions.add(permission)
                    instance.save()
    

class JobtrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "jobtracker"

    def ready(self):
        populate_default_unit_roles()
        populate_timeslot_types()