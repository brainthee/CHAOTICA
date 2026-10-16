"""Who is scheduled on a job or phase, by role (the Team tabs and the API)."""

import datetime
from decimal import Decimal

from chaotica_utils.models import User

from ..enums import TimeSlotDeliveryRole
from ..models import TimeSlot
from ..utils import assigned_role_map, phase_assigned_role_map


def get_user_schedule_breakdown(job, phase=None):
    """Build a per-user, per-role hour breakdown for a job or phase.

    Returns a list of dicts:
        [{'user': User, 'roles': [{'role_name': str, 'hours': Decimal, 'days': Decimal}], 'total_hours': Decimal, 'total_days': Decimal}]
    """

    if phase:
        slots = TimeSlot.objects.filter(phase=phase).select_related("user", "phase")
        hours_in_day = phase.get_hours_in_day()
    else:
        slots = TimeSlot.objects.filter(phase__job=job).select_related("user", "phase")
        hours_in_day = job.get_hours_in_day()

    role_names = dict(TimeSlotDeliveryRole.CHOICES)
    role_map = assigned_role_map(job, phase)  # user_pk -> [assigned role labels]

    def days(h):
        return round(h / hours_in_day, 2) if hours_in_day else Decimal(0)

    # Accumulate {user_id: {role_id: {hours, confirmed, tentative}}}
    user_data = {}
    user_objects = {}
    user_dates = {}  # user_id -> {min_start, max_end}
    for slot in slots:
        uid = slot.user_id
        user_data.setdefault(uid, {})
        user_objects.setdefault(uid, slot.user)
        cell = user_data[uid].setdefault(
            slot.deliveryRole,
            {"hours": Decimal(0), "confirmed": Decimal(0), "tentative": Decimal(0)},
        )
        hours = slot.get_business_hours()
        cell["hours"] += hours
        if slot.is_confirmed():
            cell["confirmed"] += hours
        else:
            cell["tentative"] += hours
        dates = user_dates.setdefault(uid, {"start": slot.start, "end": slot.end})
        if slot.start < dates["start"]:
            dates["start"] = slot.start
        if slot.end > dates["end"]:
            dates["end"] = slot.end

    result = []
    for uid, roles in user_data.items():
        user_roles = []
        total_hours = total_conf = total_tent = Decimal(0)
        for role_id, cell in sorted(roles.items()):
            if role_id == TimeSlotDeliveryRole.NA:
                continue
            total_hours += cell["hours"]
            total_conf += cell["confirmed"]
            total_tent += cell["tentative"]
            user_roles.append(
                {
                    "role": role_id,
                    "role_name": role_names.get(role_id, "Unknown"),
                    "hours": round(cell["hours"], 2),
                    "days": days(cell["hours"]),
                    "confirmed": round(cell["confirmed"], 2),
                    "tentative": round(cell["tentative"], 2),
                }
            )
        result.append(
            {
                "user": user_objects[uid],
                "roles": user_roles,
                "total_hours": round(total_hours, 2),
                "total_days": days(total_hours),
                "total_confirmed": round(total_conf, 2),
                "total_tentative": round(total_tent, 2),
                "assigned_roles": role_map.get(uid, []),
                "unscheduled": False,
                "start": user_dates.get(uid, {}).get("start"),
                "end": user_dates.get(uid, {}).get("end"),
            }
        )

    # Assigned-but-unscheduled people (0 booked hours) so scheduling gaps show.
    missing = [pk for pk in role_map if pk not in user_data]
    for u in User.objects.filter(pk__in=missing):
        result.append(
            {
                "user": u,
                "roles": [],
                "total_hours": Decimal(0),
                "total_days": Decimal(0),
                "total_confirmed": Decimal(0),
                "total_tentative": Decimal(0),
                "assigned_roles": role_map.get(u.pk, []),
                "unscheduled": True,
                "start": None,
                "end": None,
            }
        )

    # Scheduled people first (alphabetical), then unscheduled assignees.
    result.sort(key=lambda x: (x["unscheduled"], str(x["user"])))
    return result


# Capacity (delivery-role) columns shown on the Team tab / export, in order.
# NA is intentionally excluded (it's the "unassigned" bucket).
TEAM_CAPACITY_ROLES = [
    (TimeSlotDeliveryRole.DELIVERY, "Delivery"),
    (TimeSlotDeliveryRole.REPORTING, "Reporting"),
    (TimeSlotDeliveryRole.MANAGEMENT, "Management"),
    (TimeSlotDeliveryRole.QA, "QA"),
    (TimeSlotDeliveryRole.OVERSIGHT, "Oversight"),
    (TimeSlotDeliveryRole.DEBRIEF, "Debrief"),
    (TimeSlotDeliveryRole.CONTINGENCY, "Contingency"),
    (TimeSlotDeliveryRole.OTHER, "Other"),
]


def get_user_phase_breakdown(job):
    """Per-user, per-phase capacity breakdown across a whole job.

    Returns ``{user_pk: [phase_row, ...]}`` where each phase_row mirrors a
    ``get_user_schedule_breakdown`` entry (``roles``, totals, tentative), scoped
    to a single phase, and additionally carries the ``phase`` object and the
    user's **per-phase assigned roles** (Lead / Author / Tech QA / Pres QA).

    Rows cover the union of phases a user has booked *and* phases they're
    assigned to (so e.g. the phase someone leads shows even before it's booked;
    such a row is flagged ``unscheduled``). Rows are ordered by phase. Used to
    expand each member on the job-level Team tab into their per-phase allocation.
    """

    slots = TimeSlot.objects.filter(phase__job=job).select_related("user", "phase")
    hours_in_day = job.get_hours_in_day()
    role_names = dict(TimeSlotDeliveryRole.CHOICES)

    def days(h):
        return round(h / hours_in_day, 2) if hours_in_day else Decimal(0)

    phases = list(job.phases.all())
    phase_by_pk = {p.pk: p for p in phases}
    # Per-phase assigned roles: {phase_pk: {user_pk: [labels]}}
    phase_role_maps = {p.pk: phase_assigned_role_map(p) for p in phases}

    # {user_id: {phase_id: {role_id: {hours, confirmed, tentative}}}}
    data = {}
    for slot in slots:
        if not slot.phase_id:
            continue
        cell = (
            data.setdefault(slot.user_id, {})
            .setdefault(slot.phase_id, {})
            .setdefault(
                slot.deliveryRole,
                {"hours": Decimal(0), "confirmed": Decimal(0), "tentative": Decimal(0)},
            )
        )
        hours = slot.get_business_hours()
        cell["hours"] += hours
        if slot.is_confirmed():
            cell["confirmed"] += hours
        else:
            cell["tentative"] += hours

    def _phase_sort_key(phase):
        # Order by scheduled start, then phase number; undated phases sort last.
        return (phase.start_date or datetime.date.max, phase.phase_number or 0)

    # Every user who either booked time or is assigned a per-phase role.
    all_users = set(data.keys())
    for role_map in phase_role_maps.values():
        all_users |= set(role_map.keys())

    result = {}
    for uid in all_users:
        booked_phases = data.get(uid, {})
        # Union of phases the user booked and phases they're assigned to.
        phase_ids = set(booked_phases.keys())
        for phase_id, role_map in phase_role_maps.items():
            if uid in role_map:
                phase_ids.add(phase_id)

        rows = []
        for phase_id in phase_ids:
            phase = phase_by_pk.get(phase_id)
            if phase is None:
                continue
            roles = booked_phases.get(phase_id, {})
            user_roles = []
            total_hours = total_conf = total_tent = Decimal(0)
            for role_id, cell in sorted(roles.items()):
                if role_id == TimeSlotDeliveryRole.NA:
                    continue
                total_hours += cell["hours"]
                total_conf += cell["confirmed"]
                total_tent += cell["tentative"]
                user_roles.append(
                    {
                        "role": role_id,
                        "role_name": role_names.get(role_id, "Unknown"),
                        "hours": round(cell["hours"], 2),
                        "days": days(cell["hours"]),
                        "confirmed": round(cell["confirmed"], 2),
                        "tentative": round(cell["tentative"], 2),
                    }
                )
            rows.append(
                {
                    "phase": phase,
                    "assigned_roles": phase_role_maps.get(phase_id, {}).get(uid, []),
                    "roles": user_roles,
                    "total_hours": round(total_hours, 2),
                    "total_days": days(total_hours),
                    "total_confirmed": round(total_conf, 2),
                    "total_tentative": round(total_tent, 2),
                    "unscheduled": not roles,
                }
            )
        rows.sort(key=lambda r: _phase_sort_key(r["phase"]))
        result[uid] = rows
    return result


def _align_capacities(roles, labels):
    """Align a breakdown row's ``roles`` to the fixed capacity ``labels`` order."""
    by_name = {r["role_name"]: r for r in roles}
    return [by_name.get(label) for label in labels]


def build_team_rows(user_breakdown, phase_breakdown=None):
    """Attach aligned per-capacity cells to each breakdown entry for the Team tab.

    Each entry gains a ``capacities`` list aligned with ``TEAM_CAPACITY_ROLES``
    (a role dict from the breakdown, or ``None`` where the member has no hours in
    that capacity). When ``phase_breakdown`` (from ``get_user_phase_breakdown``)
    is supplied, each entry also gains ``phase_rows`` — a per-phase expansion,
    each with its own aligned ``capacities`` — for the job-level Team tab.
    Returns ``(capacity_labels, entries)`` for the template.
    """
    labels = [label for _id, label in TEAM_CAPACITY_ROLES]
    for entry in user_breakdown:
        entry["capacities"] = _align_capacities(entry.get("roles", []), labels)
        if phase_breakdown is not None:
            rows = phase_breakdown.get(entry["user"].pk, [])
            for row in rows:
                row["capacities"] = _align_capacities(row.get("roles", []), labels)
            entry["phase_rows"] = rows
    return labels, user_breakdown


def job_team(job):
    """The job Team tab: ``(capacity_labels, entries)``. Job-wide roles (AM /
    Deputy AM / Scoping) stay on the member; per-phase roles (Lead / Author /
    Tech QA / Pres QA) appear on each entry's ``phase_rows``."""
    from ..utils import job_assigned_role_map

    breakdown = get_user_schedule_breakdown(job)
    job_roles = job_assigned_role_map(job)
    for entry in breakdown:
        entry["assigned_roles"] = job_roles.get(entry["user"].pk, [])
    return build_team_rows(breakdown, get_user_phase_breakdown(job))


def phase_team(phase):
    """The phase Team tab: ``(capacity_labels, entries)``."""
    return build_team_rows(get_user_schedule_breakdown(phase.job, phase))


def availability_runs(users, start, end, holidays):
    """``{user_pk: [(first_day, last_day), ...]}``: runs of days each user is
    free to book — a working weekday for them, not a public holiday (their
    country's or a global one), and with no timeslot of any kind. ``holidays``
    is the window's Holiday queryset; ``start``/``end`` are datetimes."""
    from collections import defaultdict
    from datetime import timedelta

    from ..models import OrganisationalUnitMember
    from ..utils import available_day_runs

    holiday_by_country = defaultdict(set)
    global_holidays = set()
    for hol in holidays:
        if hol.country:
            holiday_by_country[str(hol.country)].add(hol.date)
        else:
            global_holidays.add(hol.date)

    # Any booking makes a day unavailable — queried unscoped, so a job-scoped
    # view still hides days the person is booked elsewhere.
    occupied = defaultdict(set)
    booked = TimeSlot.objects.filter(
        user__in=users, end__gte=start, start__lte=end
    ).values_list("user_id", "start", "end")
    for uid, slot_start, slot_end in booked:
        d, last = slot_start.date(), slot_end.date()
        while d <= last:
            occupied[uid].add(d)
            d += timedelta(days=1)

    # Working days from each user's first unit membership (default Mon–Fri).
    member_days = {}
    for m in (
        OrganisationalUnitMember.objects.filter(member__in=users)
        .select_related("unit")
        .order_by("member_id", "pk")
    ):
        member_days.setdefault(
            m.member_id, m.unit.businessHours_days or [1, 2, 3, 4, 5]
        )

    runs = {}
    for user in users:
        days = member_days.get(user.pk, [1, 2, 3, 4, 5])
        user_holidays = (
            holiday_by_country.get(str(user.country), set()) | global_holidays
        )
        runs[user.pk] = available_day_runs(
            start.date(), end.date(), days, user_holidays, occupied.get(user.pk, set())
        )
    return runs


def schedule_history(
    user, job_id=None, phase_id=None, limit=100, scan=1000, since=None
):
    """The scheduler's change log for a scope, newest first.

    A job/phase scope requires ``view_job_schedule`` on the job (else empty).
    The global log only lists actions touching someone whose schedule the
    viewer may see (it used to list everyone's)."""
    from ..models import Job, Phase, ScheduleAction
    from ..utils import can_view_job_schedule, viewable_schedule_user_pks

    qs = ScheduleAction.objects.select_related("actor", "reverted_by").order_by(
        "-created"
    )
    if since is not None:
        qs = qs.filter(created__gt=since)
    if phase_id:
        phase = Phase.objects.select_related("job__unit").filter(pk=phase_id).first()
        if not phase or not can_view_job_schedule(user, phase.job):
            return []
        return list(qs.filter(phase_id=phase_id)[:limit])
    if job_id:
        job = Job.objects.select_related("unit").filter(pk=job_id).first()
        if not job or not can_view_job_schedule(user, job):
            return []
        return list(qs.filter(job_id=job_id)[:limit])
    viewable = viewable_schedule_user_pks(user)
    out = []
    for action in qs[:scan]:
        if action._affected_user_ids() & viewable:
            out.append(action)
            if len(out) >= limit:
                break
    return out
