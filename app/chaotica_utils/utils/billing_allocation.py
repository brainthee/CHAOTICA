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


def slot_daily_hours(slot, window_start=None, window_end=None):
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

    ``window_start`` / ``window_end`` (inclusive dates) restrict the per-day
    iteration to that window. Callers that only care about a date range should
    pass it: a slot spanning years otherwise costs one ``businessDuration``
    computation per calendar day, the vast majority of which the caller then
    discards. Per-day hours are unchanged — only out-of-window days are
    skipped, not recomputed.
    """
    tz = _business_tz(slot)
    local_start = slot.start.astimezone(tz)
    local_end = slot.end.astimezone(tz)

    if local_start.date() == local_end.date():
        day = local_start.date()
        if window_start is not None and day < window_start:
            return {}
        if window_end is not None and day > window_end:
            return {}
        hours = slot.get_business_hours()
        return {day: hours} if hours > 0 else {}

    # Lazy import avoids a chaotica_utils → jobtracker cycle at module load.
    from jobtracker.models import TimeSlot

    result = {}
    day = local_start.date()
    if window_start is not None and window_start > day:
        day = window_start
    last_day = local_end.date()
    if window_end is not None and window_end < last_day:
        last_day = window_end
    while day <= last_day:
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


def _iter_days(d0, d1):
    day = d0
    while day <= d1:
        yield day
        day += datetime.timedelta(days=1)


def _add_support_draws(alloc, user, start, end, policy):
    """Overlay cashed-out support-budget hours onto the schedule allocation.

    A :class:`SupportBudgetDraw` records hours a support-team member "cashed out"
    for a period against a job. We distribute those hours across the period's
    working days, map each day to the job's effective billing code(s) (same
    duplicate-code policy), and add them to ``per_day`` / ``per_code`` tagged as
    ``kind="support"`` — so the page reads as the member's timesheet, not just
    their delivery schedule.
    """
    from jobtracker.models import SupportBudgetDraw

    draws = list(
        SupportBudgetDraw.objects.filter(
            user=user, period_start__lte=end, period_end__gte=start
        ).select_related("support_role__job")
    )
    if not draws:
        return

    per_day = alloc["per_day"]
    per_code = alloc["per_code"]

    # Resolve each job's billing assignments once. Key by pk (== the FK value
    # draw.support_role.job_id); Job's business ``id`` field is NOT its pk.
    job_cache = {}
    for draw in draws:
        job = draw.support_role.job
        if job.pk not in job_cache:
            url = job.get_absolute_url() if hasattr(job, "get_absolute_url") else None
            job_cache[job.pk] = (str(job), url, list(job.get_billing_assignments()))

    for draw in draws:
        label, url, assignments = job_cache[draw.support_role.job_id]
        days = [d for d in _iter_days(draw.period_start, draw.period_end)
                if d.weekday() < 5]
        if not days:
            continue
        daily = draw.hours_drawn / len(days)
        for day in days:
            if day < start or day > end:
                continue
            entries = per_day.setdefault(day, [])
            applicable = [a for a in assignments if code_applies_on(a, day)]
            shares = (
                _attribute_hours(applicable, daily, policy)
                if applicable else [(None, daily)]
            )
            for a, hours in shares:
                code = a.code if a is not None else None
                entries.append({
                    "code_id": code.id if code else None,
                    "code": code,
                    "hours": hours,
                    "kind": "support",
                    "targets": [{"label": label, "url": url, "kind": "job",
                                 "hours": hours}],
                })
                alloc["stats"]["support_hours"] += hours
                if code is not None:
                    summary = per_code.setdefault(code.id, {
                        "code": code, "hours": Decimal(0), "days": 0,
                        "is_chargeable": code.is_chargeable,
                        "is_internal": code.is_internal, "client_id": code.client_id,
                    })
                    summary["hours"] += hours
                    summary["days"] += 1

    alloc["per_day"] = {d: per_day[d] for d in sorted(per_day)}


def build_user_code_allocation(user, start, end, masks=None):
    """Build a user's billing-code allocation over ``[start, end]`` (inclusive).

    Returns a dict with:

    * ``per_day``: ``{date: [{code_id, code, hours, targets}, ...]}`` — for each
      day, the applicable code(s) and the hours worked that day (repeated per code
      under show-all-applicable; hours are the day's business hours, not split).
      ``targets`` is the phase(s)/project(s) that code's hours were on that day —
      ``[{label, url, kind, hours}, ...]`` — so it's clear what was worked on.
    * ``per_code``: ``{code_id: {code, hours, days, is_chargeable, is_internal,
      client_id}}`` — totals per code across the window.
    * ``uncoded``: ``{hours, days, by_target: {key: {label, url, kind, hours,
      days}}}`` — scheduled work that has **no** applicable billing code, so
      missing codes are visible rather than silently dropped.
    * ``stats``: ``{capacity_hours, scheduled_hours, coded_hours, uncoded_hours,
      unavailable_hours, internal_hours}`` — headline totals for the period so the
      numbers read against a real week (capacity = working days × hours/day).

    Multi-code days are attributed per the site ``duplicate_code_policy`` (default
    split); coded/uncoded hours on a day are reduced by any overlapping
    leave/sick time ("leave wins").
    """
    if isinstance(start, datetime.datetime):
        start = start.date()
    if isinstance(end, datetime.datetime):
        end = end.date()

    slots = list(
        user.timeslots.filter(
            start__date__lte=end, end__date__gte=start
        ).select_related("slot_type", "phase", "phase__job", "project")
    )
    # Every slot here belongs to ``user``; share the one instance so the
    # business-hours timezone/membership lookup is memoised once per user
    # rather than re-fetched for each slot (and each per-day sub-slot).
    for slot in slots:
        slot.user = user

    policy = duplicate_code_policy()
    assignments = _resolve_slot_assignments(slots)
    agg = _aggregate_slots(slots, start, end, *assignments, policy=policy)
    alloc = _finalise_allocation(agg, apply_leave_wins=True)

    # Overlay cashed-out support-budget hours so the page reads as a timesheet.
    _add_support_draws(alloc, user, start, end, policy)

    # Notional capacity for the window: working weekdays × hours per day.
    from constance import config

    hours_per_day = Decimal(str(config.DEFAULT_HOURS_IN_DAY))
    alloc["stats"]["capacity_hours"] = _business_days(start, end) * hours_per_day
    s = alloc["stats"]
    s["scheduled_hours"] = (
        s["coded_hours"] + s["uncoded_hours"]
        + s["unavailable_hours"] + s["internal_hours"]
    )
    return alloc


def _business_days(start, end):
    """Count of Mon–Fri days in the inclusive range ``[start, end]``."""
    n = 0
    day = start
    while day <= end:
        if day.weekday() < 5:
            n += 1
        day += datetime.timedelta(days=1)
    return n


def _resolve_slot_assignments(slots):
    """Resolve billing-code assignments for a batch of slots (any users).

    Gathers the distinct phase / job / project targets the slots touch and
    resolves all their assignments in **one query per target type**, returning
    ``(phase_assignments, job_assignments, project_assignments)`` as
    ``{id: [assignment, ...]}`` maps. Assignments depend only on the target,
    not the user, so a single call can serve many users' slots at once.
    """
    from jobtracker.models import BillingCodeAssignment

    phase_ids = set()
    project_ids = set()
    job_ids = set()
    for slot in slots:
        if slot.phase_id is not None:
            phase_ids.add(slot.phase_id)
            phase = slot.phase_or_none
            if phase is not None:
                job_ids.add(phase.job_id)
        elif slot.project_id is not None:
            project_ids.add(slot.project_id)

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

    return phase_assignments, job_assignments, project_assignments


_MIN_DT = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def duplicate_code_policy():
    """The site-wide policy for attributing a day's hours across multiple codes.

    One of ``split`` | ``stack`` | ``prefer_newest`` | ``prefer_oldest`` from the
    ``BILLING_DUPLICATE_CODE_POLICY`` constance setting; defaults to ``split``.
    """
    from constance import config

    value = getattr(config, "BILLING_DUPLICATE_CODE_POLICY", "split") or "split"
    if value not in ("split", "stack", "prefer_newest", "prefer_oldest"):
        return "split"
    return value


def _attribute_hours(applicable, hours, policy):
    """Split a day's ``hours`` across the applicable assignments per ``policy``.

    Returns ``[(assignment, hours), ...]`` with one entry per *distinct code*
    (assignments of the same code are collapsed to a single representative — the
    newest — so ``split`` divides across codes, not raw rows).
    """
    by_code = {}
    for a in applicable:
        cur = by_code.get(a.code_id)
        if cur is None or (a.created_at or _MIN_DT) > (cur.created_at or _MIN_DT):
            by_code[a.code_id] = a
    reps = list(by_code.values())

    if policy == "prefer_newest":
        return [(max(reps, key=lambda a: a.created_at or _MIN_DT), hours)]
    if policy == "prefer_oldest":
        return [(min(reps, key=lambda a: a.created_at or _MIN_DT), hours)]
    if policy == "split":
        share = hours / len(reps)
        return [(a, share) for a in reps]
    # stack: every code gets the full day.
    return [(a, hours) for a in reps]


def _aggregate_slots(
    slots,
    start,
    end,
    phase_assignments,
    job_assignments,
    project_assignments,
    collect_uncoded=True,
    policy="stack",
):
    """Roll a batch of one user's slots into the raw allocation accumulators.

    Returns a dict for :func:`_finalise_allocation`. Kept per-user (rather than
    folding many users together) because a code's ``days`` total is a
    *person-day* count, so the per-day maps must not mix users.

    Slots are classified per day into: **work** (a phase/project slot → coded or,
    if no applicable code, uncoded), **unavailable** (a non-working slot type —
    leave / sick / bank holiday) and **internal** (a working non-project slot —
    training, internal time). Multiple codes on a work-day are attributed per
    ``policy`` (see :func:`_attribute_hours`).

    ``collect_uncoded=False`` skips the (labelled) uncoded breakdown — the
    analytics roll-up only reads ``per_code`` and labelling a target costs a
    client query per target.
    """
    day_code_hours = {}          # day -> code_id -> hours (coded work)
    codes = {}
    day_uncoded = {}             # day -> target_key -> {hours, label, url, kind}
    day_code_targets = {}        # day -> code_id -> {target_key: {..hours}}
    day_work_hours = {}          # day -> total work-slot hours (once per slot-day)
    day_unavailable = {}         # day -> {label: hours} (leave / sick / bank hol)
    day_internal = {}            # day -> {label: hours} (working non-project)

    for slot in slots:
        slot_type = getattr(slot, "slot_type", None)
        is_work = slot.phase_id is not None or slot.project_id is not None
        daily = slot_daily_hours(slot, window_start=start, window_end=end)
        if not daily:
            continue

        if not is_work:
            # Non-project time: leave/sick (not working) vs internal (working).
            label = getattr(slot_type, "name", None) or "Internal / non-project time"
            unavailable = slot_type is not None and not slot_type.is_working
            dest = day_unavailable if unavailable else day_internal
            for day, hours in daily.items():
                bucket = dest.setdefault(day, {})
                bucket[label] = bucket.get(label, Decimal(0)) + hours
            continue

        assignments = _target_assignments(
            slot, phase_assignments, job_assignments, project_assignments
        )
        target = None  # (tkey, tlabel, turl, tkind), resolved lazily on demand
        for day, hours in daily.items():
            day_work_hours[day] = day_work_hours.get(day, Decimal(0)) + hours
            applicable = [a for a in assignments if code_applies_on(a, day)]
            if applicable:
                if collect_uncoded and target is None:
                    target = _slot_target(slot)
                for a, share in _attribute_hours(applicable, hours, policy):
                    code = a.code
                    codes[code.id] = code
                    per_day = day_code_hours.setdefault(day, {})
                    per_day[code.id] = per_day.get(code.id, Decimal(0)) + share
                    if collect_uncoded:
                        tkey, tlabel, turl, tkind = target
                        tmap = day_code_targets.setdefault(day, {}).setdefault(
                            code.id, {}
                        )
                        tentry = tmap.setdefault(
                            tkey,
                            {"label": tlabel, "url": turl, "kind": tkind,
                             "hours": Decimal(0)},
                        )
                        tentry["hours"] += share
            elif collect_uncoded:
                if target is None:
                    target = _slot_target(slot)
                tkey, tlabel, turl, tkind = target
                bucket = day_uncoded.setdefault(day, {})
                entry = bucket.setdefault(
                    tkey,
                    {"hours": Decimal(0), "label": tlabel, "url": turl, "kind": tkind},
                )
                entry["hours"] += hours

    return {
        "day_code_hours": day_code_hours,
        "codes": codes,
        "day_uncoded": day_uncoded,
        "day_code_targets": day_code_targets,
        "day_work_hours": day_work_hours,
        "day_unavailable": day_unavailable,
        "day_internal": day_internal,
    }


def _finalise_allocation(agg, apply_leave_wins=False):
    """Turn the raw accumulators into ``per_day`` / ``per_code`` / ``uncoded`` /
    ``stats``.

    When ``apply_leave_wins`` is set, a day's coded + uncoded work hours are
    scaled down by any overlapping unavailable (leave/sick) time — if the job
    overran into a day you were on leave, that day didn't actually deliver, so
    the code hours shrink accordingly (``ratio = max(0, work - unavailable) /
    work``).
    """
    day_code_hours = agg["day_code_hours"]
    codes = agg["codes"]
    day_uncoded = agg.get("day_uncoded", {})
    day_code_targets = agg.get("day_code_targets", {})
    day_work_hours = agg.get("day_work_hours", {})
    day_unavailable = agg.get("day_unavailable", {})
    day_internal = agg.get("day_internal", {})

    def _ratio(day):
        if not apply_leave_wins:
            return Decimal(1)
        work = day_work_hours.get(day, Decimal(0))
        if work <= 0:
            return Decimal(1)
        unavail = sum(day_unavailable.get(day, {}).values(), Decimal(0))
        eff = work - unavail
        if eff <= 0:
            return Decimal(0)
        if eff >= work:
            return Decimal(1)
        return eff / work

    per_day = {}
    per_code = {}
    uncoded = {"hours": Decimal(0), "days": 0, "by_target": {}}
    stats = {
        "coded_hours": Decimal(0),
        "uncoded_hours": Decimal(0),
        "unavailable_hours": Decimal(0),
        "internal_hours": Decimal(0),
        "support_hours": Decimal(0),
    }

    all_days = (
        set(day_code_hours) | set(day_uncoded)
        | set(day_unavailable) | set(day_internal)
    )
    for day in sorted(all_days):
        entries = []
        ratio = _ratio(day)

        for code_id, hours in day_code_hours.get(day, {}).items():
            h = hours * ratio
            if h <= 0:
                continue
            code = codes[code_id]
            entry = {"code_id": code_id, "code": code, "hours": h}
            tmap = day_code_targets.get(day, {}).get(code_id)
            if tmap:
                entry["targets"] = sorted(
                    (
                        {"label": t["label"], "url": t["url"], "kind": t["kind"],
                         "hours": t["hours"] * ratio}
                        for t in tmap.values()
                    ),
                    key=lambda t: (t["kind"], str(t["label"])),
                )
            entries.append(entry)
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
            summary["hours"] += h
            summary["days"] += 1
            stats["coded_hours"] += h

        for tkey, u in day_uncoded.get(day, {}).items():
            h = u["hours"] * ratio
            if h <= 0:
                continue
            entries.append(
                {
                    "code_id": None,
                    "code": None,
                    "hours": h,
                    "target_label": u["label"],
                    "target_url": u["url"],
                    "kind": u["kind"],
                }
            )
            uncoded["hours"] += h
            uncoded["days"] += 1
            tsum = uncoded["by_target"].setdefault(
                tkey,
                {"label": u["label"], "url": u["url"], "kind": u["kind"],
                 "hours": Decimal(0), "days": 0},
            )
            tsum["hours"] += h
            tsum["days"] += 1
            stats["uncoded_hours"] += h

        for label, hours in day_unavailable.get(day, {}).items():
            entries.append(
                {"code_id": None, "code": None, "hours": hours,
                 "target_label": label, "target_url": None, "kind": "unavailable"}
            )
            stats["unavailable_hours"] += hours

        for label, hours in day_internal.get(day, {}).items():
            entries.append(
                {"code_id": None, "code": None, "hours": hours,
                 "target_label": label, "target_url": None, "kind": "internal"}
            )
            stats["internal_hours"] += hours

        per_day[day] = entries

    return {"per_day": per_day, "per_code": per_code, "uncoded": uncoded, "stats": stats}


def build_code_analytics(users, start, end, internal_only=False):
    """Aggregate billing-code usage across many users over ``[start, end]``.

    Sums each code's scheduled business-hours and day-count across ``users`` and
    merges the per-code summaries. Returns:

    * ``per_code``: ``{code_id: {code, hours, days, is_chargeable, is_internal,
      client_id}}`` (``days`` here is a person-day count).
    * ``by_client``: ``{client_id or None: {client, hours, chargeable_hours,
      internal_hours, codes: set()}}``.
    * ``totals``: overall hours split chargeable / internal / other.

    Feeds the sales/client analysis and the internal-WBS operations pages.
    ``internal_only`` restricts the roll-up to client-less (WBS) codes.

    All of the data is fetched in a handful of batched queries — slots,
    org-memberships (for the business-hours timezone) and assignments are each
    read once for the whole cohort — rather than the per-user fan-out that made
    this page pathologically slow (hundreds of near-identical queries).
    """
    from jobtracker.models import TimeSlot, OrganisationalUnitMember

    if isinstance(start, datetime.datetime):
        start = start.date()
    if isinstance(end, datetime.datetime):
        end = end.date()

    users_by_id = {u.id: u for u in users}
    user_ids = list(users_by_id)

    # One query for every slot in the window across the whole cohort, bound to
    # the shared User instances so the business-hours membership memo (primed
    # below) is reused per user instead of re-queried per slot.
    slots = list(
        TimeSlot.objects.filter(
            user_id__in=user_ids, start__date__lte=end, end__date__gte=start
        ).select_related("slot_type", "phase", "phase__job", "project")
    )
    slots_by_user = {}
    for slot in slots:
        owner = users_by_id.get(slot.user_id)
        if owner is None:
            continue
        slot.user = owner
        slots_by_user.setdefault(owner.id, []).append(slot)

    # Prime each user's business-hours membership in one query (first membership
    # per user, ``unit`` joined). ``None`` is cached too, so users without a
    # membership don't fall through to a per-slot lookup.
    for uid in user_ids:
        users_by_id[uid]._business_membership_cache = None
    for m in (
        OrganisationalUnitMember.objects.filter(member_id__in=user_ids)
        .select_related("unit")
        .order_by("member_id")
    ):
        owner = users_by_id.get(m.member_id)
        if owner is not None and owner._business_membership_cache is None:
            owner._business_membership_cache = m

    # Assignments depend only on the target, so resolve them once for everyone.
    assignments = _resolve_slot_assignments(slots)
    policy = duplicate_code_policy()

    per_code = {}
    for uid, user_slots in slots_by_user.items():
        agg = _aggregate_slots(
            user_slots, start, end, *assignments,
            collect_uncoded=False, policy=policy,
        )
        alloc = _finalise_allocation(agg)
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
