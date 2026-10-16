"""
Entropy meter easter egg.

A tongue-in-cheek "operational chaos level" (0-100) derived from exactly the
same overdue/at-risk signals the dashboard surfaces as alarms — and using the
same per-role/per-category scoping (unit-wide for managers, per-QA-role for QA
holders, personal otherwise). So the score reflects the chaos the user actually
sees on their dashboard, plus a short trend of how many phases went late.

Alarm counts come from :func:`jobtracker.alarms.build_alarms` — the same
querysets the dashboard lists — so the two can't drift apart.

Purely cosmetic and read-only. Gated behind the ``ENTROPY_METER_ENABLED``
constance flag; when off the endpoint 404s.
"""

from datetime import timedelta

from django.http import JsonResponse, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from django.db.models.functions import Coalesce
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
    "no_billing_code": 3,
    # Stale work is untidy rather than urgent, so it nudges the score gently.
    "stale_stalled": 2,
    "stale_unbooked": 1,
    "stale_postponed": 1,
    "stale_no_live_phases": 2,
    "stale_dormant_jobs": 1,
}

_LABELS = {
    "delivery_overdue": "Overdue deliveries",
    "job_overdue": "Overdue jobs",
    "tqa_overdue": "Overdue tech QA",
    "pqa_overdue": "Overdue pres QA",
    "no_techqa": "Tech QA unassigned",
    "no_presqa": "Pres QA unassigned",
    "unscheduled": "Unscheduled phases",
    "no_billing_code": "Phases without a billing code",
    "stale_stalled": "Stalled phases",
    "stale_unbooked": "Never-booked phases",
    "stale_postponed": "Long-postponed phases",
    "stale_no_live_phases": "Jobs with no live phases",
    "stale_dormant_jobs": "Dormant jobs",
}

# Order factors are presented in the full UI.
_ORDER = [
    "delivery_overdue",
    "job_overdue",
    "tqa_overdue",
    "pqa_overdue",
    "no_techqa",
    "no_presqa",
    "unscheduled",
    "no_billing_code",
    "stale_stalled",
    "stale_no_live_phases",
    "stale_unbooked",
    "stale_postponed",
    "stale_dormant_jobs",
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


def compute_entropy(user, policy=None):
    """Return the user's chaos score, factor breakdown and late-delivery trend."""
    from jobtracker.alarms import build_alarms
    from jobtracker.models import OrganisationalUnit
    from jobtracker.policy import PolicyContext

    today = timezone.now().date()
    policy = policy or PolicyContext(user)
    counts = {key: qs.count() for key, qs in build_alarms(user, policy).items()}

    # The late trend uses the manager-wide / personal scope (as the alarms do).
    manager_units = (
        policy.units("can_view_jobs")
        if policy.units("change_organisationalunit").exists()
        else OrganisationalUnit.objects.none()
    )
    phase_involved = (
        Q(timeslots__user=user) | Q(report_author=user) | Q(project_lead=user)
    )


    alarm_count = sum(counts.values())
    raw = sum(counts[k] * _WEIGHTS[k] for k in counts)
    score = min(100, raw)

    factors = [
        {
            "key": k,
            "label": _LABELS[k],
            "count": counts[k],
            "points": counts[k] * _WEIGHTS[k],
        }
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
