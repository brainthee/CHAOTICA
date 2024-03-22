from django.apps import AppConfig
from django.db import connections
from .enums import DefaultTimeSlotTypes


def table_exists(table_name: str) -> bool:
    return table_name in connections["default"].introspection.table_names()


def populate_timeslot_types():
    from .models import TimeSlotType

    if table_exists("jobtracker_timeslottype"):
        for default_type in DefaultTimeSlotTypes.DEFAULTS:
            instance, created = TimeSlotType.objects.get_or_create(
                pk=default_type['pk'], defaults=default_type)
            if not created:
                for attr, value in default_type.items(): 
                    setattr(instance, attr, value)
                instance.save()


def populate_default_unit_roles():
    from .models import OrganisationalUnitRole
    from chaotica_utils.enums import UnitRoles
    from django.contrib.auth.models import Permission

    if table_exists("jobtracker_organisationalunitrole"):
        if not OrganisationalUnitRole.objects.all().count():
            for role in UnitRoles.CHOICES:
                instance, created = OrganisationalUnitRole.objects.get_or_create(
                    pk=role[0], name=role[1])
                if created:
                    if instance.name == "Manager":
                        # Make it manager
                        instance.manage_role = True
                    if instance.name == "Consultant":
                        instance.default_role = True
                    instance.bs_colour = UnitRoles.BS_COLOURS[role[0]][1]
                    for perm in UnitRoles.PERMISSIONS[role[0]][1]:
                        permission = Permission.objects.get(codename=perm.split(".")[1])
                        instance.permissions.add(permission)
                    instance.save()
    

class JobtrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "jobtracker"

    def ready(self):
        populate_default_unit_roles()
        populate_timeslot_types()