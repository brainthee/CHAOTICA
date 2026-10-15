import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def remove_schedule_from_service_delivery(apps, schema_editor):
    """
    Only Schedulers and Managers schedule: drop can_schedule_job from the
    Service Delivery role and re-sync guardian object permissions for every
    unit so existing SD members lose it. The daily
    task_sync_role_permissions_to_default keeps it that way afterwards.

    Like 0070 this uses the real models (it needs ``sync_permissions``), so a
    schema mismatch on a fresh migrate-from-empty is logged and skipped - fresh
    databases have no units to fix.
    """
    from jobtracker.models import OrganisationalUnit, OrganisationalUnitRole
    from django.contrib.auth.models import Permission

    try:
        perms = Permission.objects.filter(
            codename="can_schedule_job", content_type__app_label="jobtracker"
        )
        for role in OrganisationalUnitRole.objects.filter(name="Service Delivery"):
            role.permissions.remove(*perms)

        for unit in OrganisationalUnit.objects.all():
            unit.sync_permissions()
    except Exception as exc:
        logger.warning(
            "Skipping 0090 Service Delivery scheduling removal "
            "(no data / schema mismatch): %s",
            exc,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0089_support_draw_days"),
    ]

    operations = [
        migrations.RunPython(
            remove_schedule_from_service_delivery,
            migrations.RunPython.noop,
        ),
    ]
