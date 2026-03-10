from django.apps import AppConfig
from django.conf import settings


def populate_groups(sender, **kwargs):
    from .models import Group
    from .enums import GlobalRoles

    # create default groups
    for global_role in GlobalRoles.CHOICES:
        group, created = Group.objects.get_or_create(
            name=settings.GLOBAL_GROUP_PREFIX + global_role[1]
        )
        # Only sync permissions on startup if the group doesn't exist
        if created:
            group.sync_global_permissions()


class ChaoticaUtilsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chaotica_utils"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(populate_groups, sender=self)
