"""Timeslots and composite schedule windows."""

from django.db.models import Q
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from guardian.shortcuts import get_objects_for_user
from rest_framework import viewsets
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
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
    OrganisationalUnit,
    OrganisationalUnitMember,
    TimeSlot,
    TimeSlotType,
)
from ..base import ApiV1Mixin, BaseReadOnlyAPIViewSet
from ..serializers import (
    ScheduleSerializer,
    TimeSlotSerializer,
    TimeSlotTypeSerializer,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class TimeSlotTypeViewSet(BaseReadOnlyAPIViewSet):
    """Reference data — visible to all authenticated users."""

    serializer_class = TimeSlotTypeSerializer

    def get_base_queryset(self):
        return TimeSlotType.objects.all()


class TimeSlotViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = TimeSlotSerializer

    def get_base_queryset(self):
        return TimeSlot.objects.select_related(
            "slot_type", "phase", "project", "user"
        )

    def scope_queryset(self, queryset, user):
        # Mirrors the scheduler feeds: visible = members of units where the
        # requester holds view_users_schedule, plus the requester's own slots.
        units = get_objects_for_user(
            user, "jobtracker.view_users_schedule", klass=OrganisationalUnit
        )
        member_ids = OrganisationalUnitMember.objects.filter(
            unit__in=units
        ).values_list("member_id", flat=True)
        return queryset.filter(Q(user_id__in=member_ids) | Q(user=user)).distinct()


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

    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
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
