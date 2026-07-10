from django.db import migrations


def add_can_update_job_to_roles(apps, schema_editor):
    """
    TQA, PQA, SCOPER, and SUPERSCOPER roles were missing can_update_job,
    can_view_jobs, and view_job_schedule. Without can_update_job these users
    were blocked by job_permission_required_or_403 when not yet in the job
    team (e.g. first-time self-assignment or initial scope workflow).
    Add the missing permissions to the DB role objects and re-sync guardian
    object-level permissions for all units so existing members pick them up.

    Roles are looked up by name (stable canonical identifier) rather than PK
    to be robust against databases where PKs diverge from the enum constants.
    """
    from jobtracker.models import OrganisationalUnit, OrganisationalUnitRole
    from django.contrib.auth.models import Permission

    target_role_names = ["Tech QA'er", "Pres QA'er", "Scoper", "Super Scoper"]
    perms_to_add = ["can_update_job", "can_view_jobs", "view_job_schedule"]

    for role_name in target_role_names:
        try:
            role = OrganisationalUnitRole.objects.get(name=role_name)
        except OrganisationalUnitRole.DoesNotExist:
            continue
        for codename in perms_to_add:
            try:
                perm = Permission.objects.get(codename=codename)
                role.permissions.add(perm)
            except Permission.DoesNotExist:
                pass

    for unit in OrganisationalUnit.objects.all():
        unit.sync_permissions()


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0069_delete_accreditation"),
    ]

    operations = [
        migrations.RunPython(
            add_can_update_job_to_roles,
            migrations.RunPython.noop,
        ),
    ]
