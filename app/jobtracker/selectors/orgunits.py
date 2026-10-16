"""Org-unit data shared by the unit page and /api/v1/org-units/."""

import datetime

from django.db.models import Count
from django.utils import timezone

from ..enums import PhaseStatuses
from ..models import TimeSlot


def consultant_utilisation_4wk(unit, consultant_ids=None, today=None):
    """Per-consultant utilisation over the four weeks from this Monday:
    ``{user_id: {confirmed_days, effective_working_days, ...}}``."""
    if consultant_ids is None:
        consultant_ids = unit.get_consultant_ids()
    if not consultant_ids:
        return {}
    today = today or timezone.now().date()
    week_start = today - datetime.timedelta(days=today.weekday())
    return unit.calculate_bulk_utilization(
        week_start, week_start + datetime.timedelta(days=28), user_ids=list(consultant_ids)
    )


def utilisation_pct(util):
    """Confirmed / effective working days across ``util`` rows (the header
    tile's and Stats tab's four-week figure)."""
    confirmed = sum(m.get("confirmed_days", 0) for m in util.values())
    effective = sum(m.get("effective_working_days", 0) for m in util.values())
    return round(confirmed / effective * 100, 1) if effective else 0


def unit_member_rows(unit):
    """Current memberships (deactivated people included, flagged) with
    ``is_consultant``, ``is_deactivated``, ``util_pct`` and
    ``active_job_count`` attached, plus the unit's 4-week utilisation."""
    memberships = list(unit.get_activeMemberships(include_deactivated=True))
    member_ids = [ms.member_id for ms in memberships]
    # Only consultants get booked, so only they are worth the utilisation work.
    consultant_ids = set(unit.get_consultant_ids())
    util = consultant_utilisation_4wk(unit, consultant_ids)
    active_job_counts = {
        row["user"]: row["n"]
        for row in TimeSlot.objects.filter(
            user_id__in=member_ids,
            phase__job__unit=unit,
            phase__status__in=PhaseStatuses.ACTIVE_STATUSES,
        )
        .values("user")
        .annotate(n=Count("phase__job", distinct=True))
    }
    for ms in memberships:
        ms.is_consultant = ms.member_id in consultant_ids
        ms.is_deactivated = not ms.member.is_active
        m = util.get(ms.member_id, {})
        effective = m.get("effective_working_days", 0)
        ms.util_pct = (
            round(m.get("confirmed_days", 0) / effective * 100, 1) if effective else 0
        )
        ms.active_job_count = active_job_counts.get(ms.member_id, 0)
    return memberships, utilisation_pct(util)
