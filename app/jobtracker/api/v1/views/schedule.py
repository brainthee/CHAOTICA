"""Timeslots, schedule windows, scheduler rows, change history and deltas."""

from types import SimpleNamespace

from django.utils import timezone
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from chaotica_utils.models import User
from chaotica_utils.utils import clean_datetime

from ....forms import SchedulerFilter
from ....models import TimeSlot, TimeSlotComment, TimeSlotType
from ....selectors.schedule import schedule_history
from ....utils import (
    _filter_users_on_query,
    scheduler_member_rows,
    viewable_schedule_user_pks,
)
from .. import filters
from ..base import ApiV1Mixin, BaseReadOnlyAPIViewSet
from ..fields import make_ref
from ..schedule import (
    SCHEDULE_QUERY_PARAMS,
    build_schedule_payload,
    parse_int_param,
    parse_schedule_window,
)
from ..serializers import (
    ScheduleActionSerializer,
    ScheduleDeltasSerializer,
    ScheduleResourcesSerializer,
    ScheduleSerializer,
    ScheduleTimeSlotSerializer,
    TimeSlotCommentSerializer,
    TimeSlotSerializer,
    TimeSlotTypeSerializer,
)

FILTER_PARAMS = [
    OpenApiParameter(
        name,
        str,
        OpenApiParameter.QUERY,
        description="Scheduler filter (as the scheduler page's filter form).",
    )
    for name in SchedulerFilter.base_fields
    if name not in ("from_date", "to_date")
]
SCOPE_PARAMS = [
    OpenApiParameter(
        "job", int, description="Limit to a job (needs view_job_schedule)."
    ),
    OpenApiParameter(
        "phase", int, description="Limit to a phase (needs view_job_schedule)."
    ),
]


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


class TimeSlotCommentViewSet(BaseReadOnlyAPIViewSet):
    """Scheduler comments, visible like slots (scheduler visibility)."""

    serializer_class = TimeSlotCommentSerializer
    policy_scope = "timeslot.view"
    filterset_class = filters.TimeSlotCommentFilter
    ordering_fields = ("start", "end")

    def get_base_queryset(self):
        return TimeSlotComment.objects.all()


class _SingleObjectSchema(AutoSchema):
    """``list`` on a plain ViewSet is documented as an array by default; this
    composite returns one object."""

    def _is_list_view(self, serializer=None):
        return False


def _has_filter_params(params):
    return any(params.get(name) for name in SchedulerFilter.base_fields)


def filtered_schedule_users(request):
    """Users for the scheduler: everyone the caller may see, narrowed by the
    scheduler page's filter fields when given (same code as the page)."""
    params = request.query_params
    if _has_filter_params(params):
        form = SchedulerFilter(params)
        cleaned = form.clean() if form.is_valid() else None
        users = _filter_users_on_query(SimpleNamespace(user=request.user), cleaned)
    else:
        users = User.objects.filter(pk__in=viewable_schedule_user_pks(request.user))
    unit_id = parse_int_param(request, "unit")
    if unit_id is not None:
        users = users.filter(
            unit_memberships__unit_id=unit_id, unit_memberships__left_date__isnull=True
        )
    user_id = parse_int_param(request, "user")
    if user_id is not None:
        users = users.filter(pk=user_id)
    # A plain queryset: the filter query carries distinct/order/prefetch the
    # utilisation engine doesn't want.
    return User.objects.filter(pk__in=users.values("pk"))


class ScheduleViewSet(ApiV1Mixin, viewsets.ViewSet):
    """Read-only composite schedule feed for a date window.

    Combines work timeslots, leave, holidays, comments and per-user
    availability/utilisation for every user the requester may see under
    ``view_users_schedule`` (plus themselves), narrowed by the scheduler's
    filter fields. Built from the same core (``jobtracker.utils.collect_*``)
    as the scheduler page's feeds. For one user use ``/users/{id}/schedule/``.
    """

    schema = _SingleObjectSchema()

    @extend_schema(
        summary="Global schedule window",
        description=(
            "Not paginated — bound the result with ``start``/``end`` (default "
            "today → +28 days, max 366-day span). Narrow with ``unit``, ``user`` "
            "or any scheduler filter field (``org_units``, ``skills_specialist``, "
            "``jobs``, ``clients``…, repeated for several values)."
        ),
        parameters=SCHEDULE_QUERY_PARAMS
        + [
            OpenApiParameter("unit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("user", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ]
        + FILTER_PARAMS,
        responses=ScheduleSerializer,
    )
    def list(self, request):
        start, end = parse_schedule_window(request)
        users = filtered_schedule_users(request)
        return Response(build_schedule_payload(users, start, end, request=request))

    @extend_schema(
        summary="Scheduler rows",
        description=(
            "The people the scheduler shows for the same filters, in display "
            "order (``ordering`` / ``ordering_direction`` as on the page). "
            "Rows don't depend on the dates (beyond utilisation), so fetch once "
            "per filter."
        ),
        parameters=[
            OpenApiParameter(
                "start", OpenApiTypes.DATE, description="For utilisation."
            ),
            OpenApiParameter("end", OpenApiTypes.DATE, description="For utilisation."),
        ]
        + FILTER_PARAMS,
        responses=ScheduleResourcesSerializer,
    )
    @action(detail=False, methods=["get"])
    def resources(self, request):
        rows = scheduler_member_rows(request._request, include_html=False)
        users = {u.pk: u for u in User.objects.filter(pk__in=[r["id"] for r in rows])}
        out = []
        for row in rows:
            out.append(
                {
                    **make_ref(users[row["id"]], request),
                    "display": row["title"],
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "job_level_label": row["job_level"],
                    "org_unit": row["org_unit"],
                    "roles": row["roles"],
                    "availability": row["availability"],
                    "utilisation": row["util"],
                }
            )
        return Response({"users": out})

    @extend_schema(
        summary="Schedule change history",
        description=(
            "Newest first (max 100). With ``job``/``phase`` the history of that "
            "schedule; without, recent changes touching people whose schedule "
            "you can see."
        ),
        parameters=SCOPE_PARAMS,
        responses=ScheduleActionSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def actions(self, request):
        history = schedule_history(
            request.user,
            job_id=parse_int_param(request, "job"),
            phase_id=parse_int_param(request, "phase"),
        )
        return Response(
            ScheduleActionSerializer(
                history, many=True, context={"request": request}
            ).data
        )

    @extend_schema(
        summary="Changes since a time",
        description=(
            "Polling alternative to the live socket: committed changes after "
            "``since`` (oldest first, max 200) as upserted and removed slots. "
            "Slots of people you can't see are left out."
        ),
        parameters=SCOPE_PARAMS
        + [OpenApiParameter("since", OpenApiTypes.DATETIME, required=True)],
        responses=ScheduleDeltasSerializer,
    )
    @action(detail=False, methods=["get"])
    def deltas(self, request):
        since = clean_datetime(request.query_params.get("since"))
        if since is None:
            raise ValidationError({"since": ["Expected an ISO 8601 datetime."]})
        job_id = parse_int_param(request, "job")
        phase_id = parse_int_param(request, "phase")
        history = schedule_history(
            request.user,
            job_id=job_id,
            phase_id=phase_id,
            limit=200,
            scan=2000,
            since=since,
        )
        viewable = (
            None if (job_id or phase_id) else viewable_schedule_user_pks(request.user)
        )
        deltas = [_api_delta(a, viewable) for a in reversed(history)]
        return Response(
            ScheduleDeltasSerializer({"deltas": deltas, "now": timezone.now()}).data
        )


def _api_delta(action, viewable):
    slot_ids, comment_ids, removed_slots, removed_comments = [], [], [], []
    for item in action.payload or []:
        is_comment = item["model"] == "timeslotcomment"
        if item["after"] is None:
            (removed_comments if is_comment else removed_slots).append(item["pk"])
        else:
            (comment_ids if is_comment else slot_ids).append(item["pk"])
    slots = TimeSlot.objects.filter(pk__in=slot_ids).select_related("slot_type")
    comments = TimeSlotComment.objects.filter(pk__in=comment_ids)
    if viewable is not None:
        slots = slots.filter(user_id__in=viewable)
        comments = comments.filter(user_id__in=viewable)
    return {
        "action_id": action.pk,
        "created": action.created,
        "actor_id": action.actor_id,
        "action_type": action.action_type,
        "timeslots": slots,
        "comments": comments,
        "removed_timeslots": removed_slots,
        "removed_comments": removed_comments,
    }
