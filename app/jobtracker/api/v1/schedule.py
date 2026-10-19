"""Composite assembler + window parsing for the read-only /api/v1/ schedule.

Both the global ``/schedule/`` feed and the per-user ``/users/{id}/schedule/``
action render from :func:`build_schedule_payload`, so the two endpoints never
duplicate assembly. The underlying data comes from the shared schedule core in
``jobtracker.utils`` (``collect_schedule_slots`` / ``collect_schedule_members``)
— the same gather + utilisation logic the vis-timeline UI feeds use, so the API
and the calendar cannot drift.
"""

from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework.exceptions import ValidationError

from chaotica_utils.models.leave import LeaveRequest

from ...utils import collect_schedule_members, collect_schedule_slots
from ...selectors.schedule import availability_runs
from .fields import make_ref
from .serializers import (
    TimeSlotCommentSerializer,
    HolidaySerializer,
    ScheduleLeaveSerializer,
    ScheduleTimeSlotSerializer,
)

# Default window when ``end`` is omitted, and the hard cap on span (both in days).
DEFAULT_SCHEDULE_WINDOW_DAYS = 28
MAX_SCHEDULE_WINDOW_DAYS = 366

# Shared query-param docs for both schedule endpoints.
SCHEDULE_QUERY_PARAMS = [
    OpenApiParameter(
        "start",
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description="Window start (ISO date, YYYY-MM-DD). Defaults to today.",
        required=False,
    ),
    OpenApiParameter(
        "end",
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description=(
            "Window end (ISO date). Defaults to start + "
            f"{DEFAULT_SCHEDULE_WINDOW_DAYS} days. Span must be "
            f"{MAX_SCHEDULE_WINDOW_DAYS} days or fewer."
        ),
        required=False,
    ),
]


def parse_schedule_window(request):
    """Resolve ``(start, end)`` tz-aware datetimes from ?start / ?end.

    Defaults to today → +28d when omitted. Raises DRF ``ValidationError`` (→ 400)
    on an unparseable date, an inverted range, or an over-cap span.
    """
    today = timezone.localdate()

    start_raw = request.query_params.get("start")
    if start_raw:
        start_date = parse_date(start_raw)
        if start_date is None:
            raise ValidationError({"start": "Expected an ISO date (YYYY-MM-DD)."})
    else:
        start_date = today

    end_raw = request.query_params.get("end")
    if end_raw:
        end_date = parse_date(end_raw)
        if end_date is None:
            raise ValidationError({"end": "Expected an ISO date (YYYY-MM-DD)."})
    else:
        end_date = start_date + timedelta(days=DEFAULT_SCHEDULE_WINDOW_DAYS)

    if end_date < start_date:
        raise ValidationError({"end": "end must not be before start."})
    if (end_date - start_date).days > MAX_SCHEDULE_WINDOW_DAYS:
        raise ValidationError(
            {"end": f"Window must be {MAX_SCHEDULE_WINDOW_DAYS} days or fewer."}
        )

    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date, time.max))
    return start, end


def parse_int_param(request, name):
    """Return an int query param, or None if absent. Raises ``ValidationError``
    (→ 400) on a non-integer value rather than letting ``.filter()`` 500 on it."""
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: "Expected an integer."})


def build_schedule_payload(
    users,
    start,
    end,
    scope_phases=None,
    scope_projects=None,
    hard_scope=True,
    request=None,
    focus=None,
):
    """Assemble the composite schedule window for ``users`` in ``[start, end]``.

    ``users`` is an already-permission-scoped User **queryset**; ``start``/``end``
    are tz-aware datetimes. ``scope_*``/``hard_scope`` restrict (hard) or tag
    (soft) slots for a job/phase/project schedule. Returns a plain dict ready
    for ``Response`` — see ``ScheduleSerializer`` for the shape.
    """
    dataset = collect_schedule_slots(
        users,
        start,
        end,
        scope_phases=scope_phases,
        scope_projects=scope_projects,
        hard_scope=hard_scope,
    )
    slots = list(dataset["timeslots"])

    # start_date/end_date are DateTimeFields — filter with the aware datetimes
    # (not .date()) so leave overlapping the window is caught without coercing a
    # naive datetime.
    leave = LeaveRequest.objects.filter(
        user__in=users,
        start_date__lte=end,
        end_date__gte=start,
    ).select_related("user", "authorised_by", "timeslot")

    # The in-scope users' countries' holidays plus global (country-less) ones.
    countries = {c for c in users.values_list("country", flat=True) if c}
    holidays = dataset["holidays"].filter(
        Q(country__in=countries) | Q(country__isnull=True) | Q(country="")
    )

    # One label per phase/project the window's slots point at, so a client
    # can name slots without a request per phase.
    phases, projects = {}, {}
    for slot in slots:
        if slot.phase_id and slot.phase_id not in phases:
            phases[slot.phase_id] = make_ref(slot.phase, request)
        if slot.project_id and slot.project_id not in projects:
            projects[slot.project_id] = make_ref(slot.project, request)

    runs = availability_runs(users, start, end, holidays)

    # Slots the view doesn't centre on — a soft job/phase/project scope's
    # "other commitments", or work outside the global filter's jobs / phases /
    # clients / projects — are flagged so clients can fade or hide them.
    context = {"request": request}
    timeslots = ScheduleTimeSlotSerializer(slots, many=True, context=context).data
    scope_phase_ids = dataset["scope_phase_ids"]
    scope_project_ids = dataset["scope_project_ids"]
    for slot, row in zip(slots, timeslots):
        outside = False
        if not hard_scope:
            if scope_phase_ids is not None and slot.phase_id not in scope_phase_ids:
                outside = True
            if (
                scope_project_ids is not None
                and slot.project_id not in scope_project_ids
            ):
                outside = True
        if focus is not None and focus.is_unfocused(slot):
            outside = True
        row["out_of_scope"] = outside
    scope = None
    if (
        dataset["scope_phase_ids"] is not None
        or dataset["scope_project_ids"] is not None
    ):
        scope = {
            "phase_ids": (
                sorted(dataset["scope_phase_ids"])
                if dataset["scope_phase_ids"] is not None
                else None
            ),
            "project_ids": (
                sorted(dataset["scope_project_ids"])
                if dataset["scope_project_ids"] is not None
                else None
            ),
            "hard": hard_scope,
        }

    return {
        "start": start.date(),
        "end": end.date(),
        # collect_schedule_members already returns plain, JSON-safe dicts.
        "users": collect_schedule_members(users, start, end),
        "timeslots": timeslots,
        "leave": ScheduleLeaveSerializer(leave, many=True).data,
        "holidays": HolidaySerializer(holidays, many=True).data,
        "comments": TimeSlotCommentSerializer(
            dataset["comments"], many=True, context=context
        ).data,
        "availability": [
            {
                "user": uid,
                "runs": [{"start": a.isoformat(), "end": b.isoformat()} for a, b in r],
            }
            for uid, r in runs.items()
        ],
        "refs": {
            "phases": {str(k): v for k, v in phases.items()},
            "projects": {str(k): v for k, v in projects.items()},
        },
        "scope": scope,
    }
