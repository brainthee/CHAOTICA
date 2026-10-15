from datetime import timedelta

from django.db import migrations
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone


def cleanup_completed_jobs_with_open_phases(apps, schema_editor):
    """One-off cleanup of unfinished phases left on Completed jobs.

    Before phases were blocked from being added/cloned onto completed jobs,
    work could sit on a Completed job where the dashboard and QA/delivery
    queues never show it. Three cases:

    - **Recent in-flight work** (Pending Scheduling up to Completed, with a
      booking ending in the last 90 days, or created / status changed in the
      last 90 days): reopen the job to In Progress so it's visible again.
      (``last_modified`` isn't used: bulk re-saves touch every phase.)
    - **Stale in-flight work** (older than that): leftovers, not live work —
      archived rather than resurrected onto everyone's dashboards.
    - **Draft phases** on jobs that stay Completed: never started; archived.

    Every change is recorded as an AuditEvent (workflow / status change,
    source System), matching how the reopen transitions log.
    """
    Job = apps.get_model("jobtracker", "Job")
    Phase = apps.get_model("jobtracker", "Phase")
    TimeSlot = apps.get_model("jobtracker", "TimeSlot")
    AuditEvent = apps.get_model("chaotica_utils", "AuditEvent")
    ContentType = apps.get_model("contenttypes", "ContentType")

    # Values mirror jobtracker.enums (hardcoded so the migration is stable
    # even if the enums change later):
    #   JobStatuses.IN_PROGRESS = 7, COMPLETED = 8
    #   PhaseStatuses.DRAFT = 0, PENDING_SCHED = 1, DELIVERED = 15,
    #   ARCHIVED = 19
    JOB_IN_PROGRESS = 7
    JOB_COMPLETED = 8
    PHASE_DRAFT = 0
    PHASE_PENDING_SCHED = 1
    PHASE_DELIVERED = 15
    PHASE_ARCHIVED = 19
    PHASE_LABELS = {
        1: "Pending Scheduling", 2: "Schedule Tentative", 3: "Schedule Confirmed",
        4: "Pre-checks", 5: "Client Not Ready", 6: "Ready to Begin",
        7: "In Progress", 8: "Pending Technical QA", 9: "Tech QA",
        10: "Author Tech Updates", 11: "Pending Presentation QA",
        12: "Pres QA", 13: "Author Pres Updates",
        14: "Completed", 0: "Draft",
    }

    now = timezone.now()
    cutoff = now - timedelta(days=90)
    job_ct, _ = ContentType.objects.get_or_create(app_label="jobtracker", model="job")
    phase_ct, _ = ContentType.objects.get_or_create(app_label="jobtracker", model="phase")

    def audit(ct, obj, message):
        AuditEvent.objects.create(
            verb="status_change",
            category="workflow",
            source="system",
            actor=None,
            actor_repr="SYSTEM",
            message=message,
            target_content_type=ct,
            target_id=str(obj.pk),
            target_repr=str(getattr(obj, "phase_id", None) or getattr(obj, "title", ""))[:255],
        )

    in_flight = Phase.objects.filter(
        job__status=JOB_COMPLETED,
        status__gte=PHASE_PENDING_SCHED,
        status__lt=PHASE_DELIVERED,
    ).select_related("job")
    recent_slots = Exists(
        TimeSlot.objects.filter(phase_id=OuterRef("pk"), end__gte=cutoff)
    )
    recent = in_flight.annotate(_recent=recent_slots).filter(
        Q(_recent=True)
        | Q(created_date__gte=cutoff)
        | Q(status_changed_date__gte=cutoff)
    )
    recent_ids = set(recent.values_list("pk", flat=True))

    # 1. Recent in-flight work: reopen the job to In Progress.
    reopened_jobs = set()
    for phase in in_flight.filter(pk__in=recent_ids):
        job = phase.job
        if job.pk in reopened_jobs:
            continue
        Job.objects.filter(pk=job.pk).update(status=JOB_IN_PROGRESS)
        audit(
            job_ct, job,
            "Reopened: moved from Completed to In Progress because {} was "
            "reopened. Reason: data cleanup — {} is {} but the job was "
            "Completed".format(
                phase.phase_id, phase.phase_id, PHASE_LABELS.get(phase.status, phase.status)
            ),
        )
        reopened_jobs.add(job.pk)

    # 2. Stale in-flight work on jobs that stay Completed: archive.
    stale = list(in_flight.exclude(pk__in=recent_ids).exclude(job_id__in=reopened_jobs))
    for phase in stale:
        audit(
            phase_ct, phase,
            "Moved to Archived. Reason: data cleanup — stale {} phase on a "
            "Completed job (no activity in 90 days)".format(
                PHASE_LABELS.get(phase.status, phase.status)
            ),
        )
    Phase.objects.filter(pk__in=[p.pk for p in stale]).update(status=PHASE_ARCHIVED)

    # 3. Never-started drafts on jobs that stay Completed: archive. Drafts on
    #    jobs reopened above are left for the team to decide on.
    drafts = list(
        Phase.objects.filter(job__status=JOB_COMPLETED, status=PHASE_DRAFT)
    )
    for phase in drafts:
        audit(
            phase_ct, phase,
            "Moved to Archived. Reason: data cleanup — Draft phase that was "
            "never started on a Completed job",
        )
    Phase.objects.filter(pk__in=[p.pk for p in drafts]).update(status=PHASE_ARCHIVED)

    if reopened_jobs or stale or drafts:
        print(
            f"\n  cleanup_completed_jobs_with_open_phases: reopened "
            f"{len(reopened_jobs)} job(s) with recent in-flight phases; archived "
            f"{len(stale)} stale in-flight phase(s) and {len(drafts)} draft "
            f"phase(s) on Completed jobs."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("jobtracker", "0087_cleanup_lost_job_phases_and_stray_slots"),
        ("chaotica_utils", "0040_resync_global_role_permissions_v2"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(
            cleanup_completed_jobs_with_open_phases,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
