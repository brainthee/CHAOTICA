"""Configurable timesheet periods.

Organisations run timesheets on fixed period boundaries — commonly the 1st and
15th of the month. The boundary *days of the month* are stored in the constance
setting ``TIMESHEET_PERIOD_START_DAYS`` (e.g. ``"1,15"``), so changing the
cadence is a config change, not code.

A period runs ``[boundary_day, next_boundary_day - 1 day]``, with the last
boundary of a month wrapping into the next month. Days beyond a month's length
are clamped (e.g. a boundary of 31 lands on the 28th/30th as appropriate).
"""

from calendar import monthrange
from datetime import date, timedelta

from constance import config


def parse_period_start_days():
    """Sorted, de-duplicated boundary days from the constance setting.

    Falls back to ``[1]`` (whole-month periods) if the value is missing or
    unparseable. Days are clamped to the 1–31 range here; per-month clamping to
    the actual month length happens in :func:`_month_boundaries`.
    """
    raw = str(getattr(config, "TIMESHEET_PERIOD_START_DAYS", "1") or "1")
    days = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            d = int(part)
        except ValueError:
            continue
        if 1 <= d <= 31:
            days.add(d)
    return sorted(days) or [1]


def _month_boundaries(year, month, days):
    """Boundary dates for a given month, clamping each day to the month length
    and de-duplicating (so e.g. 30 and 31 collapse in February)."""
    dim = monthrange(year, month)[1]
    seen = set()
    out = []
    for d in days:
        clamped = min(d, dim)
        if clamped not in seen:
            seen.add(clamped)
            out.append(date(year, month, clamped))
    return out


def _surrounding_boundaries(d, days):
    """All boundary dates spanning the previous, current and next month, sorted.

    Three months is enough to always find the boundary before and after any date
    ``d``, regardless of where in the month it falls."""
    prev_y, prev_m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    next_y, next_m = (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)
    return sorted(
        _month_boundaries(prev_y, prev_m, days)
        + _month_boundaries(d.year, d.month, days)
        + _month_boundaries(next_y, next_m, days)
    )


def period_for_date(d, days=None):
    """Return ``(start, end)`` of the timesheet period containing ``d``."""
    days = days or parse_period_start_days()
    boundaries = _surrounding_boundaries(d, days)
    start = max(b for b in boundaries if b <= d)
    later = [b for b in boundaries if b > start]
    end = min(later) - timedelta(days=1)
    return start, end


def next_period(anchor, days=None):
    """The period immediately after the one containing ``anchor``."""
    days = days or parse_period_start_days()
    _, end = period_for_date(anchor, days)
    return period_for_date(end + timedelta(days=1), days)


def previous_period(anchor, days=None):
    """The period immediately before the one containing ``anchor``."""
    days = days or parse_period_start_days()
    start, _ = period_for_date(anchor, days)
    return period_for_date(start - timedelta(days=1), days)
