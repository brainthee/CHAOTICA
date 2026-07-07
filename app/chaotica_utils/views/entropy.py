"""
Entropy meter easter egg.

A tongue-in-cheek "operational chaos level" (0-100) derived from exactly the
same overdue/at-risk signals the dashboard surfaces as alarms — and using the
same per-role/per-category scoping (unit-wide for managers, per-QA-role for QA
holders, personal otherwise). So the score reflects the chaos the user actually
sees on their dashboard, plus a short trend of how many phases went late.

The alarm queries below intentionally mirror ``dashboard/views.py`` (the source
of truth for alarm scoping). If that logic changes, mirror it here.

Purely cosmetic and read-only. Gated behind the ``ENTROPY_METER_ENABLED``
constance flag; when off the endpoint 404s.
"""
from datetime import timedelta

from django.http import JsonResponse, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from django.db.models.functions import Coalesce
from guardian.shortcuts import get_objects_for_user
from constance import config

# NB: jobtracker models/enums are imported lazily inside the functions below —
# importing them at module load creates a circular import (chaotica_utils.views
# is imported while jobtracker.models is still initialising).


# Points each overdue/at-risk item adds to the chaos score (capped at 100).
_WEIGHTS = {
    "delivery_overdue": 15,
    "job_overdue": 15,
    "tqa_overdue": 10,
    "pqa_overdue": 10,
    "no_techqa": 6,
    "no_presqa": 6,
    "unscheduled": 5,
}

_LABELS = {
    "delivery_overdue": "Overdue deliveries",
    "job_overdue": "Overdue jobs",
    "tqa_overdue": "Overdue tech QA",
    "pqa_overdue": "Overdue pres QA",
    "no_techqa": "Tech QA unassigned",
    "no_presqa": "Pres QA unassigned",
    "unscheduled": "Unscheduled phases",
}

# Order factors are presented in the full UI.
_ORDER = [
    "delivery_overdue", "job_overdue", "tqa_overdue", "pqa_overdue",
    "no_techqa", "no_presqa", "unscheduled",
]

TREND_WEEKS = 8


def _level(score):
    if score >= 80:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 25:
        return "elevated"
    return "calm"


def compute_entropy(user):
    """Return the user's chaos score, factor breakdown and late-delivery trend."""
    from jobtracker.models import Job, Phase, OrganisationalUnit
    from jobtracker.enums import JobStatuses, PhaseStatuses

    today = timezone.now().date()

    # Guardian-derived unit scopes — same set the dashboard uses to scope alarms.
    units_can_view = get_objects_for_user(user, "can_view_jobs", klass=OrganisationalUnit)
    units_can_tqa = get_objects_for_user(user, "can_tqa_jobs", klass=OrganisationalUnit)
    units_can_pqa = get_objects_for_user(user, "can_pqa_jobs", klass=OrganisationalUnit)
    units_can_manage = get_objects_for_user(user, "change_organisationalunit", klass=OrganisationalUnit)
    units_can_schedule = get_objects_for_user(user, "can_schedule_job", klass=OrganisationalUnit)

    # Unit managers see every alarm unit-wide; everyone else only for phases/jobs
    # they're personally on (plus QA/scheduler roles for those categories).
    manager_units = units_can_view if units_can_manage.exists() else OrganisationalUnit.objects.none()

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

    def _alarm_phases(unit_scope):
        return Phase.objects.filter(
            Q(job__unit__in=unit_scope) | phase_involved,
            status__in=PhaseStatuses.ACTIVE_STATUSES,
            job__status__in=JobStatuses.ACTIVE_STATUSES,
        ).distinct()

    base_mgr = _alarm_phases(manager_units)
    base_tqa = _alarm_phases(manager_units | units_can_tqa)
    base_pqa = _alarm_phases(manager_units | units_can_pqa)
    base_sched = _alarm_phases(manager_units | units_can_schedule)

    counts = {}
    counts["delivery_overdue"] = (
        base_mgr.annotate(db=Coalesce("desired_delivery_date", "_delivery_date"))
        .filter(db__lt=today).count()
    )
    counts["tqa_overdue"] = (
        base_tqa.annotate(db=Coalesce("due_to_techqa_set", "_due_to_techqa"))
        .filter(
            db__lt=today,
            status__in=[
                PhaseStatuses.IN_PROGRESS, PhaseStatuses.PENDING_TQA,
                PhaseStatuses.QA_TECH, PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
            ],
        ).count()
    )
    counts["pqa_overdue"] = (
        base_pqa.annotate(db=Coalesce("due_to_presqa_set", "_due_to_presqa"))
        .filter(
            db__lt=today,
            status__in=[
                PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES,
                PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
            ],
        ).count()
    )
    counts["no_techqa"] = base_tqa.filter(
        techqa_by__isnull=True,
        status__in=[
            PhaseStatuses.PENDING_TQA, PhaseStatuses.QA_TECH,
            PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
        ],
    ).count()
    counts["no_presqa"] = base_pqa.filter(
        presqa_by__isnull=True,
        status__in=[
            PhaseStatuses.PENDING_PQA, PhaseStatuses.QA_PRES,
            PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
        ],
    ).count()
    counts["unscheduled"] = base_sched.filter(
        status__in=[
            PhaseStatuses.SCHEDULED_TENTATIVE, PhaseStatuses.SCHEDULED_CONFIRMED,
            PhaseStatuses.PRE_CHECKS, PhaseStatuses.CLIENT_NOT_READY,
            PhaseStatuses.READY_TO_BEGIN, PhaseStatuses.IN_PROGRESS,
        ],
        timeslots__isnull=True,
    ).count()
    counts["job_overdue"] = (
        Job.objects.filter(
            Q(unit__in=manager_units) | job_involved,
            status__in=JobStatuses.ACTIVE_STATUSES,
        )
        .annotate(db=Coalesce("desired_delivery_date", "_delivery_date"))
        .filter(db__lt=today)
        .distinct()
        .count()
    )

    alarm_count = sum(counts.values())
    raw = sum(counts[k] * _WEIGHTS[k] for k in counts)
    score = min(100, raw)

    factors = [
        {"key": k, "label": _LABELS[k], "count": counts[k], "points": counts[k] * _WEIGHTS[k]}
        for k in _ORDER
        if counts.get(k)
    ]

    return {
        "score": score,
        "level": _level(score),
        "alarm_count": alarm_count,
        "factors": factors,
        "trend": _late_trend(today, manager_units, phase_involved),
        "trend_weeks": TREND_WEEKS,
    }


def _late_trend(today, manager_units, phase_involved):
    """Count phases (in scope) that went late, bucketed by week (oldest first)."""
    from jobtracker.models import Phase

    window_start = today - timedelta(weeks=TREND_WEEKS)
    # Include non-active phases too, so deliveries that landed late still count.
    candidates = (
        Phase.objects.filter(Q(job__unit__in=manager_units) | phase_involved)
        .annotate(db=Coalesce("desired_delivery_date", "_delivery_date"))
        .filter(db__gte=window_start, db__lte=today)
        .distinct()
    )

    buckets = [0] * TREND_WEEKS
    for phase in candidates:
        if not phase.is_delivery_late:
            continue
        due = phase.delivery_date
        if not due:
            continue
        weeks_ago = (today - due).days // 7
        if 0 <= weeks_ago < TREND_WEEKS:
            buckets[TREND_WEEKS - 1 - weeks_ago] += 1
    return buckets


@login_required
def entropy_status(request):
    if not getattr(config, "ENTROPY_METER_ENABLED", False):
        return HttpResponseNotFound()
    return JsonResponse(compute_entropy(request.user))
