from django.db import migrations
from django.db.models import Exists, OuterRef
from django.utils import timezone


def cleanup_lost_job_phases_and_stray_slots(apps, schema_editor):
    """One-off cleanup for data left behind by the old cascade bugs.

    - ``Job.to_lost()`` cancelled phases in memory but never saved them (T-01),
      so phases of lost jobs stayed live. Cancel them and erase their slots.
    - Cancelled/postponed/deleted phases could keep (or regain) timeslots.
      Erase them.
    - Bulk slot deletes left phases Scheduled with nothing booked. Move them
      back to Pending Scheduling.
    """
    Phase = apps.get_model("jobtracker", "Phase")
    TimeSlot = apps.get_model("jobtracker", "TimeSlot")

    # Values mirror jobtracker.enums (hardcoded so the migration is stable
    # even if the enums change later):
    #   JobStatuses.LOST = 9
    #   PhaseStatuses.PENDING_SCHED = 1, SCHEDULED_TENTATIVE = 2,
    #   SCHEDULED_CONFIRMED = 3, DELIVERED = 15, CANCELLED = 16,
    #   POSTPONED = 17, DELETED = 18, ARCHIVED = 19
    JOB_LOST = 9
    PHASE_PENDING_SCHED = 1
    PHASE_SCHEDULED = [2, 3]
    PHASE_DELIVERED = 15
    PHASE_CANCELLED = 16
    PHASE_INACTIVE = [16, 17, 18, 19]
    PHASE_CLOSED_NO_SLOTS = [16, 17, 18]

    # 1. Live phases on lost jobs -> Cancelled, slots erased.
    lost_phases = Phase.objects.filter(
        job__status=JOB_LOST, status__lt=PHASE_DELIVERED
    ).exclude(status__in=PHASE_INACTIVE)
    lost_ids = list(lost_phases.values_list("pk", flat=True))
    lost_slots = TimeSlot.objects.filter(phase_id__in=lost_ids).delete()[0]
    lost_updated = Phase.objects.filter(pk__in=lost_ids).update(
        status=PHASE_CANCELLED, cancellation_date=timezone.now()
    )

    # 2. Slots on cancelled/postponed/deleted phases.
    stray_slots = TimeSlot.objects.filter(
        phase__status__in=PHASE_CLOSED_NO_SLOTS
    ).delete()[0]

    # 3. Scheduled phases with nothing booked -> Pending Scheduling.
    empty_scheduled = Phase.objects.filter(status__in=PHASE_SCHEDULED).exclude(
        Exists(TimeSlot.objects.filter(phase_id=OuterRef("pk")))
    )
    reverted = empty_scheduled.update(status=PHASE_PENDING_SCHED)

    if lost_updated or stray_slots or reverted:
        print(
            f"\n  cleanup_lost_job_phases_and_stray_slots: cancelled {lost_updated} "
            f"phase(s) on lost jobs (removed {lost_slots} timeslot(s)); removed "
            f"{stray_slots} timeslot(s) on closed phases; moved {reverted} "
            f"Scheduled phase(s) with no slots to Pending Scheduling."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0086_support_profile_required"),
    ]

    operations = [
        migrations.RunPython(
            cleanup_lost_job_phases_and_stray_slots,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
