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
from .serializers import (
    HolidaySerializer,
    LeaveRequestSerializer,
    TimeSlotSerializer,
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


def build_schedule_payload(users, start, end):
    """Assemble the composite schedule window for ``users`` in ``[start, end]``.

    ``users`` is an already-permission-scoped User **queryset**; ``start``/``end``
    are tz-aware datetimes. Returns a plain dict ready for ``Response`` — see
    ``ScheduleSerializer`` for the shape.
    """
    dataset = collect_schedule_slots(users, start, end)

    # start_date/end_date are DateTimeFields — filter with the aware datetimes
    # (not .date()) so leave overlapping the window is caught without coercing a
    # naive datetime.
    leave = LeaveRequest.objects.filter(
        user__in=users,
        start_date__lte=end,
        end_date__gte=start,
    ).select_related("user", "authorised_by", "timeslot")

    # Scope holidays to the countries of the in-scope users (plus global,
    # country-less holidays), mirroring how the vis-timeline feed matches a
    # holiday to a user by country — rather than returning every country's
    # holidays regardless of who the caller can see.
    countries = {c for c in users.values_list("country", flat=True) if c}
    holidays = dataset["holidays"].filter(
        Q(country__in=countries) | Q(country__isnull=True)
    )

    return {
        "start": start.date(),
        "end": end.date(),
        # collect_schedule_members already returns plain, JSON-safe dicts.
        "users": collect_schedule_members(users, start, end),
        "timeslots": TimeSlotSerializer(dataset["timeslots"], many=True).data,
        "leave": LeaveRequestSerializer(leave, many=True).data,
        "holidays": HolidaySerializer(holidays, many=True).data,
    }
