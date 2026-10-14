from django.db import migrations


def resync_global_permissions(apps, schema_editor):
    """Re-apply GlobalRoles.PERMISSIONS after fixing mistyped codenames
    (view_users_qualifications, chaotica_utils.manage_user) that were being
    silently dropped, so the corrected grants apply on deploy rather than at
    the next daily sync. Fresh installs have no permissions yet (they're
    created post_migrate) and are skipped - populate_groups handles them.
    """
    from django.conf import settings
    from django.contrib.auth.models import Permission
    from chaotica_utils.enums import GlobalRoles

    # Real Group model (not the historical one) for sync_global_permissions().
    from chaotica_utils.models import Group

    if not Permission.objects.exists():
        return

    for global_role in GlobalRoles.CHOICES:
        try:
            group = Group.objects.get(
                name=settings.GLOBAL_GROUP_PREFIX + global_role[1]
            )
        except Group.DoesNotExist:
            continue
        group.sync_global_permissions()


class Migration(migrations.Migration):

    dependencies = [
        ("chaotica_utils", "0039_retag_schedule_audit_events"),
        ("jobtracker", "0087_cleanup_lost_job_phases_and_stray_slots"),
    ]

    operations = [
        migrations.RunPython(
            resync_global_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
