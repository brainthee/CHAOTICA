from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


def populate_timeslot_types(sender, **kwargs):
    from .models import TimeSlotType
    from .enums import DefaultTimeSlotTypes

    if not TimeSlotType.objects.all().count():
        # Don't run if we already have types in the DB
        for default_type in DefaultTimeSlotTypes.DEFAULTS:
            instance, created = TimeSlotType.objects.get_or_create(
                pk=default_type["pk"], defaults=default_type
            )
            if created:
                for attr, value in default_type.items():
                    setattr(instance, attr, value)
                instance.save()


def populate_default_unit_roles(sender, **kwargs):
    from .models import OrganisationalUnitRole
    from chaotica_utils.enums import UnitRoles
    from django.contrib.auth.models import Permission

    if not OrganisationalUnitRole.objects.all().count():
        # Don't run if we already have roles in the DB
        for role in UnitRoles.DEFAULTS:
            if role["pk"] == 0:
                continue
            instance, created = OrganisationalUnitRole.objects.get_or_create(
                pk=role["pk"], name=role["name"]
            )
            if created:
                for attr, value in role.items():
                    setattr(instance, attr, value)

                for perm in UnitRoles.PERMISSIONS[role["pk"]-1][1]:
                    if perm:
                        codeword = perm
                        if "." in perm:
                            codeword = perm.split(".")[1]
                        if Permission.objects.filter(codename=codeword).exists():
                            permission = Permission.objects.get(codename=codeword)
                            instance.permissions.add(permission)
                        else:
                            logger.error(
                                "ERROR: Unknown Permission - {full}".format(
                                    full=perm
                                )
                            )
                instance.save()


class JobtrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "jobtracker"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(populate_default_unit_roles, sender=self)
        post_migrate.connect(populate_timeslot_types, sender=self)

        # Import signal handlers
        from . import signals  # noqa: F401
        try:
            from .signals import skill_cache  # noqa: F401
        except ImportError:
            pass  # Signals module doesn't exist yet
