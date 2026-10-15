"""Dashboard alarms — the single source of truth.

Used by the dashboard Alarms tab (as lists), the entropy meter (as counts) and
the late-notification task (to stop reminding about stale work). Two groups:

* **Overdue** — live work that's late or missing something (QA reviewer,
  billing code, bookings).
* **Stale** — work that has stopped moving: nobody is going to make it "on
  time", it needs closing off or picking back up. Stale items are left out of
  the overdue lists so those only show genuinely late work.

Scoping is per role and per category:

* "On the team" (scheduled on / lead / report author of a phase, or on the
  job's account/scoping team) -> every alarm for that phase/job.
* Unit managers (change_organisationalunit) -> all alarms unit-wide.
* TQA / PQA role -> TQA / PQA alarms unit-wide.
* Schedulers (can_schedule_job) -> unscheduled, missing
  billing code and stale-demand alarms unit-wide.
"""

from datetime import timedelta

from constance import config
from django.db.models import Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from guardian.shortcuts import get_objects_for_user

from .enums import JobStatuses, PhaseStatuses

#: Booking-driven phase statuses (Schedule Tentative to In Progress): if
#: nothing is booked any more and the status hasn't moved, the work has
#: stalled. QA / awaiting-delivery statuses are excluded on purpose — they
#: normally have no bookings while waiting on a reviewer, so they stay in the
#: overdue alarms (and keep their late reminders).
STALLABLE_STATUSES = [
    PhaseStatuses.SCHEDULED_TENTATIVE,
    PhaseStatuses.SCHEDULED_CONFIRMED,
    PhaseStatuses.PRE_CHECKS,
    PhaseStatuses.CLIENT_NOT_READY,
    PhaseStatuses.READY_TO_BEGIN,
    PhaseStatuses.IN_PROGRESS,
]

#: Job statuses before work starts (scoping and sign-off).
EARLY_JOB_STATUSES = [
    JobStatuses.DRAFT,
    JobStatuses.PENDING_SCOPE,
    JobStatuses.SCOPING,
    JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED,
    JobStatuses.PENDING_SCOPING_SIGNOFF,
]

#: Job statuses that should end in Completed once their phases are done.
DELIVERY_JOB_STATUSES = [
    JobStatuses.SCOPING_COMPLETE,
    JobStatuses.PENDING_START,
    JobStatuses.IN_PROGRESS,
]


def _cutoff(days):
    return timezone.now() - timedelta(days=days)


def stalled_phase_q(days=None):
    """Booking-driven phases (see STALLABLE_STATUSES) with no status change for
    ``days`` and no booking that ends within the last ``days`` (or later)."""
    from .models import TimeSlot

    cutoff = _cutoff(config.STALE_PHASE_DAYS if days is None else days)
    recent_or_future = TimeSlot.objects.filter(phase_id=OuterRef("pk"), end__gte=cutoff)
    return (
        Q(status__in=STALLABLE_STATUSES, status_changed_date__lt=cutoff)
        & ~Q(Exists(recent_or_future))
    )


def unbooked_phase_q(days=None):
    """Pending Scheduling phases whose wanted delivery date passed ``days``
    ago and that were never booked — demand that's probably dead."""
    from .models import TimeSlot

    cutoff = _cutoff(config.STALE_PHASE_DAYS if days is None else days).date()
    return Q(
        status=PhaseStatuses.PENDING_SCHED,
        stale_wanted_date__lt=cutoff,
    ) & ~Q(Exists(TimeSlot.objects.filter(phase_id=OuterRef("pk"))))


def _with_wanted_date(qs):
    return qs.annotate(
        stale_wanted_date=Coalesce("desired_delivery_date", "_delivery_date")
    )


def long_postponed_q(days=None):
    """Postponed phases (which block their job completing) left for ``days``."""
    cutoff = _cutoff(config.STALE_POSTPONED_DAYS if days is None else days)
    return Q(status=PhaseStatuses.POSTPONED, status_changed_date__lt=cutoff)


def no_live_phases_job_q():
    """Jobs at/after scope sign-off whose phases are all finished but which
    can't complete — e.g. every phase was cancelled, so there's nothing to
    deliver. Someone needs to close the job (Lost/Delete) or add work."""
    from .models import Phase

    unfinished = Phase.objects.filter(job_id=OuterRef("pk")).filter(
        Q(status__lt=PhaseStatuses.DELIVERED) | Q(status=PhaseStatuses.POSTPONED)
    )
    return (
        Q(status__in=DELIVERY_JOB_STATUSES)
        & Q(Exists(Phase.objects.filter(job_id=OuterRef("pk"))))
        & ~Q(Exists(unfinished))
    )


def dormant_job_q(days=None):
    """Jobs still in Draft / scoping / sign-off with no status change for
    ``days`` — prospects that probably went nowhere."""
    cutoff = _cutoff(config.STALE_JOB_DAYS if days is None else days)
    return Q(status__in=EARLY_JOB_STATUSES, status_changed_date__lt=cutoff)


def stalled_phase_ids(phase_qs):
    """IDs of stalled phases within ``phase_qs`` (for the late-notification task)."""
    return set(phase_qs.filter(stalled_phase_q()).values_list("pk", flat=True))


def build_alarms(user):
    """All alarm querysets for ``user``: ``{key: queryset}``.

    Querysets are unevaluated: the dashboard lists them (with its own
    select_related), the entropy meter counts them.
    """
    from .models import Job, OrganisationalUnit, Phase

    today = timezone.now().date()

    def _units(perm):
        return get_objects_for_user(user, perm, klass=OrganisationalUnit)

    units_can_view = _units("can_view_jobs")
    units_can_tqa = _units("can_tqa_jobs")
    units_can_pqa = _units("can_pqa_jobs")
    units_can_manage = _units("change_organisationalunit")
    units_can_schedule = _units("can_schedule_job")
    manager_units = (
        units_can_view if units_can_manage.exists() else OrganisationalUnit.objects.none()
    )

    phase_involved = (
        Q(timeslots__user=user) | Q(report_author=user) | Q(project_lead=user)
    )
    job_involved = (
        Q(phases__timeslots__user=user)
        | Q(phases__report_author=user)
        | Q(phases__project_lead=user)
        | Q(scoped_by=user)
        | Q(account_manager=user)
        | Q(dep_account_manager=user)
    )

    def _phases(unit_scope, statuses=PhaseStatuses.ACTIVE_STATUSES):
        # Phases the user is on the team of, plus phases in the role-scoped units.
        return Phase.objects.filter(
            Q(job__unit__in=unit_scope) | phase_involved,
            status__in=statuses,
            job__status__in=JobStatuses.ACTIVE_STATUSES,
        ).distinct()

    def _not_stale(qs):
        # Stalled / dead-demand phases are reported in the stale group instead.
        return _with_wanted_date(qs).exclude(stalled_phase_q()).exclude(unbooked_phase_q())

    base_mgr = _phases(manager_units)
    base_tqa = _phases(manager_units | units_can_tqa)
    base_pqa = _phases(manager_units | units_can_pqa)
    base_sched = _phases(manager_units | units_can_schedule)
    jobs = Job.objects.filter(
        Q(unit__in=manager_units) | job_involved,
        status__in=JobStatuses.ACTIVE_STATUSES,
    ).distinct()

    alarms = {}

    # --- Overdue ---
    alarms["delivery_overdue"] = _not_stale(base_mgr).filter(stale_wanted_date__lt=today)
    alarms["tqa_overdue"] = _not_stale(base_tqa).annotate(
        db_tqa_date=Coalesce("due_to_techqa_set", "_due_to_techqa")
    ).filter(
        db_tqa_date__lt=today,
        status__in=[
            PhaseStatuses.IN_PROGRESS, PhaseStatuses.PENDING_TQA,
            PhaseStatuses.QA_TECH, PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
        ],
    )
    alarms["pqa_overdue"] = _not_stale(base_pqa).annotate(
        db_pqa_date=Coalesce("due_to_presqa_set", "_due_to_presqa")
    ).filter(
        db_pqa_date__lt=today,
        status__in=[
            PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES,
            PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
        ],
    )
    alarms["no_techqa"] = base_tqa.filter(
        techqa_by__isnull=True,
        status__in=[
            PhaseStatuses.PENDING_TQA, PhaseStatuses.QA_TECH,
            PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
        ],
    )
    alarms["no_presqa"] = base_pqa.filter(
        presqa_by__isnull=True,
        status__in=[
            PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES,
            PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
        ],
    )
    alarms["unscheduled"] = base_sched.filter(
        status__in=[
            PhaseStatuses.SCHEDULED_TENTATIVE, PhaseStatuses.SCHEDULED_CONFIRMED,
            PhaseStatuses.PRE_CHECKS, PhaseStatuses.CLIENT_NOT_READY,
            PhaseStatuses.READY_TO_BEGIN, PhaseStatuses.IN_PROGRESS,
        ],
        timeslots__isnull=True,
    )
    # Not base_sched: that's ACTIVE-only, and completed phases still need a
    # code for the time already booked.
    alarms["no_billing_code"] = (
        Phase.objects.filter(
            Q(job__unit__in=manager_units | units_can_schedule) | phase_involved,
            status__in=PhaseStatuses.CODE_REQUIRED_STATUSES,
            job__status__in=JobStatuses.ACTIVE_STATUSES,
        )
        .filter(Phase.missing_billing_code_q())
        .distinct()
    )
    alarms["job_overdue"] = (
        jobs.exclude(no_live_phases_job_q())
        .exclude(dormant_job_q())
        .annotate(db_delivery_date=Coalesce("desired_delivery_date", "_delivery_date"))
        .filter(db_delivery_date__lt=today)
    )

    # --- Stale ---
    from .models import TimeSlot

    last_booking = Subquery(
        TimeSlot.objects.filter(phase_id=OuterRef("pk")).order_by("-end").values("end")[:1]
    )
    alarms["stale_stalled"] = (
        _phases(manager_units, STALLABLE_STATUSES)
        .filter(stalled_phase_q())
        .annotate(last_booking=last_booking)
    )
    alarms["stale_unbooked"] = _with_wanted_date(
        _phases(manager_units | units_can_schedule, [PhaseStatuses.PENDING_SCHED])
    ).filter(unbooked_phase_q())
    alarms["stale_postponed"] = _phases(manager_units, [PhaseStatuses.POSTPONED]).filter(
        long_postponed_q()
    )
    alarms["stale_no_live_phases"] = jobs.filter(no_live_phases_job_q())
    alarms["stale_dormant_jobs"] = jobs.filter(dormant_job_q())

    return alarms


#: Alarm keys in the stale group (everything else is "overdue").
STALE_KEYS = (
    "stale_stalled",
    "stale_unbooked",
    "stale_postponed",
    "stale_no_live_phases",
    "stale_dormant_jobs",
)
