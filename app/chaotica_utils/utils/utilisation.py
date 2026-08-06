"""
Centralised utilisation calculation.

This module is the **single source of truth** for how staff utilisation is
calculated across CHAOTICA. Every place that reports a utilisation figure (per
user, per organisational unit, per team) delegates the day-classification and
percentage maths to :func:`calculate_utilisation` here, so the formula is
defined and changed in exactly one place.

Formula
-------
``utilisation = confirmed_delivery_days / effective_working_days * 100``

where::

    effective_working_days = working_days - public_holidays - non_working_slot_days

* **working_days** — calendar days that fall on the org unit's configured
  working weekdays (``businessHours_days``).
* **public_holidays** — days with a ``Holiday`` record for the user's country
  (or a global ``country=NULL`` holiday).
* **non_working_slot_days** — working, non-holiday days on which the user has at
  least one timeslot whose ``slot_type.is_working`` is ``False`` (annual leave,
  sick, bank holiday booked on the scheduler, or any custom non-working type).
* **confirmed_delivery_days** — the remaining working days on which the user has
  at least one timeslot that is *confirmed delivery*: linked to a phase whose status is at
  least ``SCHEDULED_CONFIRMED`` (but not cancelled/postponed/deleted), **or** linked to a
  ``deliverable`` project in the ``CONFIRMED`` state (see :func:`classify_delivery_slot`).
  This lets teams whose work lives on internal ``Project``s (e.g. RM-imported EU teams)
  register utilisation.

Rules
-----
* **Non-working wins (day granularity).** Because the scheduler works at
  day granularity, a day touched by *any* non-working slot is removed from the
  denominator entirely — even if a confirmed delivery slot also exists that day
  — and therefore never enters the numerator either.
* **Zero effective working days.** A user with no effective working days in the
  period (e.g. fully on leave) has ``utilisation_percentage = None`` and is
  excluded from team/unit averages, so they do not drag the average to 0%.
* Tentative bookings and internal working time (training, catch-ups, and
  non-deliverable / ``INTERNAL``-state projects) do **not** count toward utilisation; they
  are reported separately. Only ``CONFIRMED`` + ``deliverable`` project work counts.

Implementation note
--------------------
The engine represents each day in the period as a bit in a Python integer, so a
timeslot spanning several days becomes a single mask built in O(1) via bit
shifts, and day counts are C-speed ``int.bit_count()`` pop-counts. This avoids
per-user allocation and per-day Python loops, keeping bulk (whole-unit)
calculations fast without a third-party dependency. ``int.bit_count()`` requires
Python 3.10+ (satisfied by the Django 5.2 baseline).
"""

import json
from datetime import datetime, date

# Single source of truth for the human-readable explanation of the formula.
# Surfaced in the UI (via the ``defaults`` context processor) and in the site
# documentation (via mkdocstrings), so both stay in sync with the code.
UTILISATION_FORMULA_DESCRIPTION = (
    "Utilisation = confirmed client-delivery days ÷ effective working days × 100. "
    "Confirmed delivery means a confirmed phase booking or a deliverable project in the "
    "Confirmed state. Effective working days excludes weekends, public holidays, and any day "
    "blocked by a non-working slot (annual leave, sick, etc.). Tentative bookings and internal "
    "working time (training, catch-ups, internal projects) do not count toward utilisation."
)


def classify_delivery_slot(slot):
    """Classify a timeslot for utilisation from a ``.values()`` dict.

    Single source of truth for *what counts as delivery*. Accepts the keys
    ``phase__status``, ``project__state``, ``project__deliverable`` and
    ``slot_type__is_working`` and returns the three flags the engine consumes.

    Confirmed delivery = a slot on a phase at/above ``SCHEDULED_CONFIRMED``, **or** a slot on a
    ``deliverable`` project in the ``CONFIRMED`` state. Tentative = a phase below
    ``SCHEDULED_CONFIRMED`` or a ``deliverable`` project in the ``TENTATIVE`` state. Internal
    (non-deliverable / ``INTERNAL``-state) projects are neither, so they stay "internal" time
    and never enter the utilisation numerator.

    Phases in an *ignored* status (cancelled, postponed, deleted) never count as
    delivery even though those status values are numerically ``>= SCHEDULED_CONFIRMED``.
    """
    # Lazy import to avoid a chaotica_utils → jobtracker import cycle at module load.
    from jobtracker.enums import PhaseStatuses, ProjectState

    phase_status = slot.get("phase__status")
    p_state = slot.get("project__state")
    p_deliverable = bool(slot.get("project__deliverable"))

    # A slot on a cancelled/postponed/deleted phase is not real delivery — those
    # statuses are all numerically >= SCHEDULED_CONFIRMED, so without this guard
    # their leftover slots would be miscounted as confirmed delivery. ARCHIVED is
    # deliberately NOT ignored: it is genuinely-delivered past work that should
    # still count toward historical utilisation.
    phase_ignored = phase_status in PhaseStatuses.IGNORED_STATUSES
    phase_conf = (
        phase_status is not None
        and not phase_ignored
        and phase_status >= PhaseStatuses.SCHEDULED_CONFIRMED
    )
    phase_tent = (
        phase_status is not None
        and not phase_ignored
        and phase_status < PhaseStatuses.SCHEDULED_CONFIRMED
    )
    proj_conf = p_deliverable and p_state == ProjectState.CONFIRMED
    proj_tent = p_deliverable and p_state == ProjectState.TENTATIVE

    is_confirmed = bool(phase_conf or proj_conf)
    is_tentative = bool((phase_tent or proj_tent) and not is_confirmed)
    return {
        "is_confirmed": is_confirmed,
        "is_tentative": is_tentative,
        "is_non_working_slot": slot.get("slot_type__is_working") is False,
    }


def _as_date(value):
    """Coerce a date/datetime to a plain ``date``."""
    if isinstance(value, datetime):
        return value.date()
    return value


def _percentage(part, whole, decimal_places=2):
    """Safe percentage helper — returns 0 when the denominator is zero."""
    if not whole:
        return 0
    return round((part / whole) * 100, decimal_places)


def _normalise_working_days(working_days):
    """
    Coerce a working-days config into a set of ISO weekday ints.

    ``businessHours_days`` is a JSONField that normally holds a list such as
    ``[1, 2, 3, 4, 5]``, but legacy/bad data can be a bare int or a JSON string.
    Be defensive so a single malformed unit can't crash utilisation everywhere.
    """
    if working_days is None:
        return set()
    if isinstance(working_days, str):
        try:
            working_days = json.loads(working_days)
        except (ValueError, TypeError):
            return set()
    if isinstance(working_days, int):
        return {working_days}
    try:
        return set(working_days)
    except TypeError:
        return set()


def build_period_masks(start_date, end_date, working_days, holiday_dates):
    """
    Build the day-index masks that are constant for a whole calculation call.

    Splitting this out lets bulk callers compute the (shared) working-weekday
    mask once and reuse it across every user in the period, and holiday masks
    once per country, rather than rebuilding them per user.

    Args:
        start_date: start of the period (date or datetime, inclusive).
        end_date: end of the period (date or datetime, inclusive).
        working_days: iterable of ISO weekday ints (1=Mon … 7=Sun).
        holiday_dates: iterable of ``date`` objects that are public holidays.

    Returns:
        dict with:
            num_days: number of days in the (inclusive) period.
            start: the period start as a ``date``.
            working_days: ``set`` of the working weekday ints.
            full_range_mask, working_weekday_mask, holiday_mask,
            base_effective_mask: integer bit masks over day indices.
    """
    start = _as_date(start_date)
    end = _as_date(end_date)
    working_days = _normalise_working_days(working_days)
    holiday_dates = set(_as_date(h) for h in (holiday_dates or []))

    num_days = (end - start).days + 1
    if num_days < 0:
        num_days = 0

    full_range_mask = (1 << num_days) - 1

    working_weekday_mask = 0
    holiday_mask = 0
    for i in range(num_days):
        d = date.fromordinal(start.toordinal() + i)
        if (d.weekday() + 1) in working_days:
            working_weekday_mask |= 1 << i
        if d in holiday_dates:
            holiday_mask |= 1 << i

    # Working weekdays that are not public holidays.
    base_effective_mask = working_weekday_mask & ~holiday_mask & full_range_mask

    return {
        "num_days": num_days,
        "start": start,
        "working_days": working_days,
        "full_range_mask": full_range_mask,
        "working_weekday_mask": working_weekday_mask,
        "holiday_mask": holiday_mask,
        "base_effective_mask": base_effective_mask,
    }


def _slot_mask(slot, period_start, num_days):
    """Return the day-index mask a slot covers within the period (O(1))."""
    s = (_as_date(slot["start"]) - period_start).days
    e = (_as_date(slot["end"]) - period_start).days
    if s < 0:
        s = 0
    if e > num_days - 1:
        e = num_days - 1
    if s > e:
        return 0
    length = e - s + 1
    return ((1 << length) - 1) << s


def calculate_utilisation(
    slots, start_date, end_date, working_days, holiday_dates, masks=None
):
    """
    Calculate utilisation statistics for a single user over a date range.

    Args:
        slots: iterable of dicts, each with keys:
            ``start`` / ``end`` (date or datetime, the slot's span),
            ``is_confirmed`` (bool — phase status >= SCHEDULED_CONFIRMED),
            ``is_tentative`` (bool — has a phase below SCHEDULED_CONFIRMED),
            ``is_non_working_slot`` (bool — ``slot_type.is_working`` is False).
        start_date / end_date: inclusive period bounds (date or datetime).
        working_days: iterable of ISO weekday ints (1=Mon … 7=Sun).
        holiday_dates: iterable of ``date`` objects (public holidays).
        masks: optional pre-built masks from :func:`build_period_masks` (bulk
            callers pass this to avoid rebuilding shared masks per user).

    Returns:
        dict of day counts and percentages. ``utilisation_percentage`` and
        ``confirmed_percentage`` are ``None`` when there are no effective
        working days; every other percentage is ``0`` in that case so template
        chart data stays numeric.
    """
    if masks is None:
        masks = build_period_masks(start_date, end_date, working_days, holiday_dates)

    num_days = masks["num_days"]
    period_start = masks["start"]
    full_range_mask = masks["full_range_mask"]
    working_weekday_mask = masks["working_weekday_mask"]
    holiday_mask = masks["holiday_mask"]
    base_effective_mask = masks["base_effective_mask"]

    # Accumulate day masks by category across all of the user's slots.
    confirmed_mask = 0
    tentative_mask = 0
    non_working_mask = 0
    internal_mask = 0

    for slot in slots:
        mask = _slot_mask(slot, period_start, num_days)
        if not mask:
            continue
        if slot["is_non_working_slot"]:
            non_working_mask |= mask
        if slot["is_confirmed"]:
            confirmed_mask |= mask
        if slot["is_tentative"]:
            tentative_mask |= mask
        # "Internal" = a working slot that is neither confirmed nor tentative
        # delivery (e.g. training, catch-up, internal project, unassigned).
        if (
            not slot["is_non_working_slot"]
            and not slot["is_confirmed"]
            and not slot["is_tentative"]
        ):
            internal_mask |= mask

    # Non-working wins: strip those days out of the effective working days.
    effective_mask = base_effective_mask & ~non_working_mask

    # --- Day counts ---
    total_days = num_days
    working_days_count = base_effective_mask.bit_count()
    holiday_days = (full_range_mask & holiday_mask).bit_count()
    non_working_days = num_days - working_weekday_mask.bit_count()

    effective_working_days = effective_mask.bit_count()
    non_working_slot_days = (base_effective_mask & non_working_mask).bit_count()

    confirmed_days = (effective_mask & confirmed_mask).bit_count()
    tentative_days = (effective_mask & tentative_mask).bit_count()
    internal_days = (effective_mask & internal_mask).bit_count()

    scheduled_days = (
        effective_mask & (confirmed_mask | tentative_mask | internal_mask)
    ).bit_count()
    available_days = effective_working_days - scheduled_days

    # Backwards-compatible "no client delivery today" count: any working,
    # non-holiday day with a phase-less slot (leave/sick or internal).
    non_delivery_days = (
        base_effective_mask & (non_working_mask | internal_mask)
    ).bit_count()

    # --- Percentages ---
    if effective_working_days:
        utilisation_percentage = round(
            (confirmed_days / effective_working_days) * 100, 2
        )
    else:
        # No effective working days (e.g. fully on leave): utilisation is
        # undefined, not 0 — so it can be excluded from averages.
        utilisation_percentage = None

    data = {
        "total_days": total_days,
        "working_days": working_days_count,
        "non_working_days": non_working_days,
        "holiday_days": holiday_days,
        "effective_working_days": effective_working_days,
        "non_working_slot_days": non_working_slot_days,
        "available_days": available_days,
        "scheduled_days": scheduled_days,
        "tentative_days": tentative_days,
        "confirmed_days": confirmed_days,
        "internal_days": internal_days,
        # Backwards-compatible key (feeds existing chart data).
        "non_delivery_days": non_delivery_days,
        "utilisation_percentage": utilisation_percentage,
        "confirmed_percentage": utilisation_percentage,
        "tentative_percentage": _percentage(tentative_days, effective_working_days),
        "internal_percentage": _percentage(internal_days, effective_working_days),
        "available_percentage": _percentage(available_days, effective_working_days),
        # These keep the old denominator (working_days) because their numerators
        # can include days outside the effective set (leave days).
        "non_working_slot_percentage": _percentage(
            non_working_slot_days, working_days_count
        ),
        "non_delivery_percentage": _percentage(non_delivery_days, working_days_count),
        # How much of the (non-weekend) period is actual working time.
        "working_percentage": _percentage(
            working_days_count, total_days - non_working_days
        ),
    }
    return data


def aggregate_utilisation(per_user_stats):
    """
    Build a summary across many users' stats dicts.

    Users with zero effective working days are excluded from the utilisation
    average (they are on leave for the whole period, not under-utilised), but
    their day counts still contribute to the totals.

    Args:
        per_user_stats: iterable of stats dicts from :func:`calculate_utilisation`.

    Returns:
        dict of summary totals and averages.
    """
    stats = list(per_user_stats)
    num_users = len(stats)

    sum_keys = [
        "working_days",
        "effective_working_days",
        "non_working_slot_days",
        "available_days",
        "scheduled_days",
        "tentative_days",
        "confirmed_days",
        "internal_days",
        "non_delivery_days",
    ]
    totals = {key: 0 for key in sum_keys}
    for s in stats:
        for key in sum_keys:
            totals[key] += s.get(key, 0) or 0

    total_effective = totals["effective_working_days"]

    summary = {
        "num_users": num_users,
        "avg_working_days": (
            round(totals["working_days"] / num_users, 2) if num_users else 0
        ),
        "total_working_days": totals["working_days"],
        "total_effective_working_days": total_effective,
        "total_non_working_slot_days": totals["non_working_slot_days"],
        "total_available_days": totals["available_days"],
        "total_scheduled_days": totals["scheduled_days"],
        "total_tentative_days": totals["tentative_days"],
        "total_confirmed_days": totals["confirmed_days"],
        "total_internal_days": totals["internal_days"],
        "total_non_delivery_days": totals["non_delivery_days"],
        "avg_utilisation_percentage": _percentage(
            totals["confirmed_days"], total_effective
        ),
        "avg_available_percentage": _percentage(
            totals["available_days"], total_effective
        ),
    }
    return summary
