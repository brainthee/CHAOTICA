"""Timeslots and composite schedule windows."""

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import viewsets
from rest_framework.response import Response

from chaotica_utils.models import User

from ....utils import viewable_schedule_user_pks
from ..schedule import (
    SCHEDULE_QUERY_PARAMS,
    build_schedule_payload,
    parse_int_param,
    parse_schedule_window,
)

from ....models import (
    TimeSlot,
    TimeSlotType,
)
from .. import filters
from ..base import ApiV1Mixin, BaseReadOnlyAPIViewSet
from ..serializers import (
    ScheduleSerializer,
    TimeSlotSerializer,
    TimeSlotTypeSerializer,
)


class TimeSlotTypeViewSet(BaseReadOnlyAPIViewSet):
    """Reference data — visible to all authenticated users."""

    serializer_class = TimeSlotTypeSerializer
    policy_scope = None  # reference data

    def get_base_queryset(self):
        return TimeSlotType.objects.all()


class TimeSlotViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = TimeSlotSerializer
    policy_scope = "timeslot.view"
    filterset_class = filters.TimeSlotFilter
    ordering_fields = ("start", "end")

    def get_base_queryset(self):
        return TimeSlot.objects.select_related(
            "slot_type", "phase__job", "project", "user"
        )


class _SingleObjectSchema(AutoSchema):
    """``list`` on a plain ViewSet is documented as an array by default; this
    composite returns one object."""

    def _is_list_view(self, serializer=None):
        return False


class ScheduleViewSet(ApiV1Mixin, viewsets.ViewSet):
    """Read-only composite schedule feed for a date window.

    Combines work timeslots, leave, holidays and per-user availability/utilisation
    for every user the requester may see under ``view_users_schedule`` (plus
    themselves). Renders the clean REST shape from the same shared core
    (``jobtracker.utils.collect_schedule_*``) the vis-timeline UI feeds use, so
    the API and the calendar cannot drift. For a single user use the
    ``/users/{id}/schedule/`` action instead.
    """

    schema = _SingleObjectSchema()

    @extend_schema(
        summary="Global schedule window",
        description=(
            "Composite schedule (timeslots, leave, holidays, per-user "
            "availability) for the caller's visible users over a date window. "
            "Not paginated — bound the result with ``start``/``end`` (default "
            "today → +28 days, max 366-day span). Optionally narrow with "
            "``unit`` and ``user``."
        ),
        parameters=SCHEDULE_QUERY_PARAMS
        + [
            OpenApiParameter(
                "unit",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Restrict to members of this org unit (within scope).",
                required=False,
            ),
            OpenApiParameter(
                "user",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Restrict to a single user id (within scope).",
                required=False,
            ),
        ],
        responses=ScheduleSerializer,
    )
    def list(self, request):
        start, end = parse_schedule_window(request)
        users = User.objects.filter(pk__in=viewable_schedule_user_pks(request.user))

        unit_id = parse_int_param(request, "unit")
        if unit_id is not None:
            users = users.filter(unit_memberships__unit_id=unit_id).distinct()
        user_id = parse_int_param(request, "user")
        if user_id is not None:
            users = users.filter(pk=user_id)

        return Response(build_schedule_payload(users, start, end))
