import logging

from django.db import migrations

logger = logging.getLogger(__name__)


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

    This is a one-time best-effort backfill for already-populated databases.
    It imports and uses the *real* models (it needs the ``sync_permissions``
    method, which historical models don't have), so on a fresh migrate-from-
    empty the real model can carry columns not yet present at this point in
    history (e.g. ``is_deleted``, added later in 0077) and the query 1054s.
    Fresh databases have no units to backfill, so any such mismatch is wrapped
    and skipped rather than breaking new installs / CI / demo rebuilds.
    """
    from jobtracker.models import OrganisationalUnit, OrganisationalUnitRole
    from django.contrib.auth.models import Permission

    target_role_names = ["Tech QA'er", "Pres QA'er", "Scoper", "Super Scoper"]
    perms_to_add = ["can_update_job", "can_view_jobs", "view_job_schedule"]

    try:
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
    except Exception as exc:
        # Schema mismatch on a fresh DB (nothing to backfill) or missing
        # tables/columns - skip. Populated DBs applied this successfully before
        # later schema changes landed.
        logger.warning(
            "Skipping 0070 permission backfill (no data / schema mismatch): %s", exc
        )


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
