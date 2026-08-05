from django.db import migrations


def cleanup_phases_of_deleted_jobs(apps, schema_editor):
    """One-off cleanup for phases orphaned by the old soft-delete bug.

    Before the fix, ``Job.to_delete()`` moved a job to DELETED but never
    persisted the cascade to its phases, so those phases stayed in an active
    status (and kept generating late-notification emails and timeslots). This
    finds any phase whose parent job is DELETED/ARCHIVED but is not itself
    DELETED, moves it to DELETED, and erases its scheduled timeslots.
    """
    Phase = apps.get_model("jobtracker", "Phase")
    TimeSlot = apps.get_model("jobtracker", "TimeSlot")

    # Values mirror jobtracker.enums (hardcoded so the migration is stable
    # even if the enums change later):
    #   JobStatuses.DELETED = 10, JobStatuses.ARCHIVED = 11
    #   PhaseStatuses.DELETED = 18
    JOB_DEAD_STATUSES = [10, 11]
    PHASE_DELETED = 18

    stale_phases = Phase.objects.filter(
        job__status__in=JOB_DEAD_STATUSES
    ).exclude(status=PHASE_DELETED)

    phase_ids = list(stale_phases.values_list("pk", flat=True))
    if not phase_ids:
        return

    slots_deleted = TimeSlot.objects.filter(phase_id__in=phase_ids).delete()
    phases_updated = stale_phases.update(status=PHASE_DELETED)

    print(
        f"\n  cleanup_phases_of_deleted_jobs: set {phases_updated} phase(s) to "
        f"DELETED and removed {slots_deleted[0]} timeslot(s)."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0075_remove_historicalorganisationalunit_approval_required_and_more"),
    ]

    operations = [
        migrations.RunPython(
            cleanup_phases_of_deleted_jobs,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
