from django.db import migrations


def resync_global_permissions(apps, schema_editor):
    """Re-apply GlobalRoles.PERMISSIONS to existing global-role groups.

    ``populate_groups`` (post_migrate) only syncs permissions for *newly
    created* groups, so on an existing database the USER role never picks up
    newly-added permissions (project creation + report create/view). This
    forces a one-off re-sync for every global-role group that already exists.
    Fresh installs are unaffected (they hit the created=True sync path).
    """
    from django.conf import settings
    from chaotica_utils.enums import GlobalRoles

    # Use the real Group model (not the historical one) so the
    # sync_global_permissions() helper + guardian assign_perm are available.
    from chaotica_utils.models import Group

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
        ("chaotica_utils", "0035_alias_utf8mb4"),
        # Ensure the reporting permissions/content types exist before we try to
        # assign reporting.add_report / reporting.view_report.
        ("reporting", "0007_reportrun"),
        ("jobtracker", "0074_historicalproject_deliverable_and_more"),
    ]

    operations = [
        migrations.RunPython(
            resync_global_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
