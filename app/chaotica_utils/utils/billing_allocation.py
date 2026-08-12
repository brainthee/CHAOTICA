"""Per-user billing-code allocation engine.

Sibling to :mod:`chaotica_utils.utils.utilisation`. Answers the question *"which
billing code(s) should this person book against, on which days, for how many
hours?"* — deliberately **not** a timesheet. It is a view over the schedule:

* a user's timeslots give the *when* and *how many hours* (per day),
* the billing-code assignments on the slot's phase / job / project give the
  *which code(s)*, honouring the phase-override rule and the optional date
  range on each assignment.

Two deliberate policies (confirmed decisions):

* **Override** — a phase's own assignments replace the job's for that phase;
  phases with none inherit the job's (see
  :meth:`Phase.get_effective_billing_assignments`).
* **Show-all-applicable** — a day may map to several codes (undated + dated, or
  overlapping dated ranges). We surface *all* of them rather than picking a
  single winner, so overlaps are visible, not silently resolved. Consequently a
  code's total hours can exceed the hours actually worked when ranges overlap.
"""

import datetime
from decimal import Decimal


def code_applies_on(assignment, day):
    """Whether a :class:`BillingCodeAssignment` applies on ``day``.

    Undated (both bounds ``None``) ⇒ always true within the target span. A null
    bound is open-ended on that side; otherwise ``start <= day <= end``.
    """
    start = assignment.start_date
    end = assignment.end_date
    if start is not None and day < start:
        return False
    if end is not None and day > end:
        return False
    return True


def _business_tz(slot):
    return slot._get_business_tz()


def slot_daily_hours(slot):
    """Split a timeslot into ``{date: business_hours}`` per calendar day.

    The one genuinely new primitive here: it runs the *same*
    ``businessDuration`` / lunch logic as :meth:`TimeSlot.get_business_hours`,
    but per day, by clipping the slot at business-timezone midnight into
    per-day sub-slots and reusing ``get_business_hours`` on each. The sum over
    days therefore equals the whole-slot ``get_business_hours()`` — we never
    approximate with ``total / num_days``.

    Single-day slots short-circuit to ``{day: slot.get_business_hours()}``.
    Days that resolve to zero business hours (e.g. a weekend day inside a
    multi-day span) are omitted.
    """
    tz = _business_tz(slot)
    local_start = slot.start.astimezone(tz)
    local_end = slot.end.astimezone(tz)

    if local_start.date() == local_end.date():
        hours = slot.get_business_hours()
        return {local_start.date(): hours} if hours > 0 else {}

    # Lazy import avoids a chaotica_utils → jobtracker cycle at module load.
    from jobtracker.models import TimeSlot

    result = {}
    day = local_start.date()
    while day <= local_end.date():
        midnight_next = datetime.datetime.combine(
            day + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz
        )
        midnight_this = datetime.datetime.combine(
            day, datetime.time.min, tzinfo=tz
        )
        seg_start = max(local_start, midnight_this)
        seg_end = min(local_end, midnight_next)
        if seg_start < seg_end:
            # Ephemeral single-day slot reuses the exact hours logic.
            sub = TimeSlot(user=slot.user, start=seg_start, end=seg_end)
            hours = sub.get_business_hours()
            if hours > 0:
                result[day] = hours
        day += datetime.timedelta(days=1)
    return result


def _slot_target(slot):
    """Identify the engagement a slot belongs to, for labelling uncoded work.

    Returns ``(key, label, url, kind)`` where ``kind`` is ``'phase'`` |
    ``'project'`` | ``'other'`` (leave / internal time that has no engagement to
    hang a billing code off). ``key`` is a hashable used to group a day's uncoded
    hours by engagement.
    """
    if getattr(slot, "phase_id", None) is not None:
        phase = slot.phase_or_none
        if phase is not None:
            url = phase.get_absolute_url() if hasattr(phase, "get_absolute_url") else None
            return ("phase", phase.id), str(phase), url, "phase"
    if getattr(slot, "project_id", None) is not None:
        project = getattr(slot, "project", None)
        if project is not None:
            url = project.get_absolute_url() if hasattr(project, "get_absolute_url") else None
            return ("project", project.id), str(project), url, "project"
    slot_type = getattr(slot, "slot_type", None)
    label = (getattr(slot_type, "name", None) or "Internal / non-project time")
    return ("other", getattr(slot, "slot_type_id", None)), label, None, "other"


def _target_assignments(slot, phase_assignments, job_assignments, project_assignments):
    """Effective assignments for a single slot, applying the override rule.

    ``phase_assignments`` / ``job_assignments`` / ``project_assignments`` are
    pre-built ``{id: [assignment, ...]}`` maps so no per-slot query is needed.
    """
    phase_id = getattr(slot, "phase_id", None)
    project_id = getattr(slot, "project_id", None)

    if phase_id is not None:
        own = phase_assignments.get(phase_id)
        if own:
            return own
        # Inherit the job's assignments.
        job_id = None
        phase = slot.phase_or_none
        if phase is not None:
            job_id = phase.job_id
        return job_assignments.get(job_id, [])
    if project_id is not None:
        return project_assignments.get(project_id, [])
    return []


def build_user_code_allocation(user, start, end, masks=None):
    """Build a user's billing-code allocation over ``[start, end]`` (inclusive).

    Returns a dict with:

    * ``per_day``: ``{date: [{code_id, code, hours}, ...]}`` — for each day, the
      applicable code(s) and the hours worked that day (repeated per code under
      show-all-applicable; hours are the day's business hours, not split).
    * ``per_code``: ``{code_id: {code, hours, days, is_chargeable, is_internal,
      client_id}}`` — totals per code across the window.
    * ``uncoded``: ``{hours, days, by_target: {key: {label, url, kind, hours,
      days}}}`` — scheduled work that has **no** applicable billing code, so
      missing codes are visible rather than silently dropped.
    """
    from jobtracker.models import BillingCodeAssignment

    if isinstance(start, datetime.datetime):
        start = start.date()
    if isinstance(end, datetime.datetime):
        end = end.date()

    slots = list(
        user.timeslots.filter(
            start__date__lte=end, end__date__gte=start
        ).select_related("slot_type", "user", "phase", "phase__job", "project")
    )

    # Gather the distinct targets touched by the user's slots, then resolve all
    # their assignments in one batched query per target type.
    phase_ids = set()
    project_ids = set()
    for slot in slots:
        if slot.phase_id is not None:
            phase_ids.add(slot.phase_id)
        elif slot.project_id is not None:
            project_ids.add(slot.project_id)

    job_ids = set()
    phase_job = {}
    for slot in slots:
        if slot.phase_id is not None:
            phase = slot.phase_or_none
            if phase is not None:
                phase_job[slot.phase_id] = phase.job_id
                job_ids.add(phase.job_id)

    phase_assignments = {}
    job_assignments = {}
    project_assignments = {}

    def _bucket(bucket, key, assignment):
        bucket.setdefault(key, []).append(assignment)

    for a in BillingCodeAssignment.objects.filter(
        phase_id__in=phase_ids
    ).select_related("code", "code__client"):
        _bucket(phase_assignments, a.phase_id, a)
    for a in BillingCodeAssignment.objects.filter(
        job_id__in=job_ids
    ).select_related("code", "code__client"):
        _bucket(job_assignments, a.job_id, a)
    for a in BillingCodeAssignment.objects.filter(
        project_id__in=project_ids
    ).select_related("code", "code__client"):
        _bucket(project_assignments, a.project_id, a)

    # day -> code_id -> hours (coded work)
    day_code_hours = {}
    codes = {}
    # day -> target_key -> {hours, label, url, kind} (scheduled work with no
    # applicable code on that day — surfaced so missing codes are visible).
    day_uncoded = {}

    for slot in slots:
        assignments = _target_assignments(
            slot, phase_assignments, job_assignments, project_assignments
        )
        daily = slot_daily_hours(slot)
        if not daily:
            continue
        tkey, tlabel, turl, tkind = _slot_target(slot)
        for day, hours in daily.items():
            if day < start or day > end:
                continue
            applicable = [a for a in assignments if code_applies_on(a, day)]
            if applicable:
                for a in applicable:
                    code = a.code
                    codes[code.id] = code
                    per_day = day_code_hours.setdefault(day, {})
                    per_day[code.id] = per_day.get(code.id, Decimal(0)) + hours
            else:
                bucket = day_uncoded.setdefault(day, {})
                entry = bucket.setdefault(
                    tkey,
                    {"hours": Decimal(0), "label": tlabel, "url": turl, "kind": tkind},
                )
                entry["hours"] += hours

    return _finalise_allocation(day_code_hours, codes, day_uncoded)


def _finalise_allocation(day_code_hours, codes, day_uncoded=None):
    day_uncoded = day_uncoded or {}
    per_day = {}
    per_code = {}
    uncoded = {"hours": Decimal(0), "days": 0, "by_target": {}}

    for day in sorted(set(day_code_hours) | set(day_uncoded)):
        entries = []
        for code_id, hours in day_code_hours.get(day, {}).items():
            code = codes[code_id]
            entries.append({"code_id": code_id, "code": code, "hours": hours})
            summary = per_code.setdefault(
                code_id,
                {
                    "code": code,
                    "hours": Decimal(0),
                    "days": 0,
                    "is_chargeable": code.is_chargeable,
                    "is_internal": code.is_internal,
                    "client_id": code.client_id,
                },
            )
            summary["hours"] += hours
            summary["days"] += 1
        for tkey, u in day_uncoded.get(day, {}).items():
            entries.append(
                {
                    "code_id": None,
                    "code": None,
                    "hours": u["hours"],
                    "target_label": u["label"],
                    "target_url": u["url"],
                    "kind": u["kind"],
                }
            )
            uncoded["hours"] += u["hours"]
            uncoded["days"] += 1
            tsum = uncoded["by_target"].setdefault(
                tkey,
                {"label": u["label"], "url": u["url"], "kind": u["kind"],
                 "hours": Decimal(0), "days": 0},
            )
            tsum["hours"] += u["hours"]
            tsum["days"] += 1
        per_day[day] = entries

    return {"per_day": per_day, "per_code": per_code, "uncoded": uncoded}


def build_code_analytics(users, start, end, internal_only=False):
    """Aggregate billing-code usage across many users over ``[start, end]``.

    Sums each code's scheduled business-hours and day-count across ``users`` by
    running :func:`build_user_code_allocation` per user and merging the
    ``per_code`` summaries. Returns:

    * ``per_code``: ``{code_id: {code, hours, days, is_chargeable, is_internal,
      client_id}}`` (``days`` here is a person-day count).
    * ``by_client``: ``{client_id or None: {client, hours, chargeable_hours,
      internal_hours, codes: set()}}``.
    * ``totals``: overall hours split chargeable / internal / other.

    Feeds the sales/client analysis and the internal-WBS operations pages.
    ``internal_only`` restricts the roll-up to client-less (WBS) codes.
    """
    per_code = {}
    for user in users:
        alloc = build_user_code_allocation(user, start, end)
        for code_id, summary in alloc["per_code"].items():
            if internal_only and summary["client_id"] is not None:
                continue
            agg = per_code.setdefault(
                code_id,
                {
                    "code": summary["code"],
                    "hours": Decimal(0),
                    "days": 0,
                    "is_chargeable": summary["is_chargeable"],
                    "is_internal": summary["is_internal"],
                    "client_id": summary["client_id"],
                },
            )
            agg["hours"] += summary["hours"]
            agg["days"] += summary["days"]

    by_client = {}
    totals = {"hours": Decimal(0), "chargeable": Decimal(0), "internal": Decimal(0)}
    for summary in per_code.values():
        code = summary["code"]
        client = code.client
        bucket = by_client.setdefault(
            summary["client_id"],
            {
                "client": client,
                "hours": Decimal(0),
                "chargeable_hours": Decimal(0),
                "internal_hours": Decimal(0),
                "codes": set(),
            },
        )
        bucket["hours"] += summary["hours"]
        bucket["codes"].add(code.id)
        totals["hours"] += summary["hours"]
        if summary["is_chargeable"]:
            bucket["chargeable_hours"] += summary["hours"]
            totals["chargeable"] += summary["hours"]
        if summary["is_internal"]:
            bucket["internal_hours"] += summary["hours"]
            totals["internal"] += summary["hours"]

    return {"per_code": per_code, "by_client": by_client, "totals": totals}
