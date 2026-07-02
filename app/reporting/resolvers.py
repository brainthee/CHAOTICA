"""
Whitelisted computed-field resolvers for the reporting engine.

The generic report engine resolves most columns via ORM lookups
(``queryset.values(field_path)``). Some values are model properties/methods
that ``.values()`` cannot express - e.g. scheduled days split by delivery role,
or the comma-joined list of assigned engineers. Those are computed here.

Only keys present in ``REPORTING_RESOLVERS`` can be invoked by a report
definition, and any per-row arguments (e.g. which delivery role to total) are
baked into the closure. This keeps report definitions from being able to call
arbitrary model methods - a ``DataField`` merely references a resolver *key*,
never a method name.

Each resolver also declares ``select_related`` / ``prefetch_related`` hints.
``DataService`` unions the hints of every resolver used by a report and applies
them once, so the whole result set is fetched without per-row (N+1) queries.
Resolvers therefore iterate already-prefetched relations in Python rather than
calling model helpers that ``.filter()`` the relation (which would re-hit the
DB per row).
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from jobtracker.enums import PhaseStatuses, TimeSlotDeliveryRole


@dataclass(frozen=True)
class Resolver:
    """A computed field: a callable plus the query hints it needs."""

    fn: Callable  # (instance, ctx) -> value
    select_related: tuple = ()
    prefetch_related: tuple = ()


def _user_name(user):
    if user is None:
        return ""
    full = user.get_full_name()
    return full.strip() if full and full.strip() else str(user)


def _days_by_role(role):
    """Total scheduled *days* for a delivery role, from prefetched timeslots.

    Mirrors ``Phase.get_total_scheduled_days_by_type`` but iterates the
    prefetched ``timeslots`` in Python instead of ``.filter()``-ing them (which
    ignores the prefetch and re-queries per phase).
    """

    def resolve(phase, ctx):
        hours = Decimal(0)
        for slot in phase.timeslots.all():
            if slot.deliveryRole == role:
                hours += slot.get_business_hours()
        hid = phase.get_hours_in_day()
        return round(hours / hid, 2) if hid else 0

    return resolve


def _assigned_engineers(phase, ctx):
    names = {
        _user_name(slot.user)
        for slot in phase.timeslots.all()
        if slot.user_id
    }
    names.discard("")
    return ", ".join(sorted(names))


def _project_manager(phase, ctx):
    # "Project Manager" in the chaser email is the job's account manager (the
    # demand manager), falling back to the phase project lead if unset.
    pm = phase.job.account_manager or phase.project_lead
    return _user_name(pm) if pm else ""


_PHASE_STATUS_LABELS = dict(PhaseStatuses.CHOICES)


REPORTING_RESOLVERS = {
    "phase.days_testing": Resolver(
        _days_by_role(TimeSlotDeliveryRole.DELIVERY),
        prefetch_related=("timeslots", "timeslots__user__unit_memberships__unit"),
    ),
    "phase.days_reporting": Resolver(
        _days_by_role(TimeSlotDeliveryRole.REPORTING),
        prefetch_related=("timeslots", "timeslots__user__unit_memberships__unit"),
    ),
    "phase.assigned_engineers": Resolver(
        _assigned_engineers,
        prefetch_related=("timeslots__user",),
    ),
    "phase.start_date": Resolver(
        lambda phase, ctx: phase.start_date,
    ),
    "phase.project_manager": Resolver(
        _project_manager,
        select_related=("job__account_manager", "project_lead"),
    ),
    "phase.status_label": Resolver(
        lambda phase, ctx: _PHASE_STATUS_LABELS.get(phase.status, ""),
    ),
}
