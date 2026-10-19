"""Timeslots, schedule windows, scheduler rows, change history and deltas."""

from types import SimpleNamespace

from django.core.exceptions import SuspiciousOperation
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
    SchedulerFocus,
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
    ScheduleBoundsSerializer,
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


def filtered_schedule_users(request, with_focus=False):
    """Users for the scheduler: everyone the caller may see, narrowed by the
    scheduler page's filter fields when given (same code as the page). With
    ``with_focus`` also returns the filter's ``SchedulerFocus`` (or None)."""
    params = request.query_params
    focus = None
    if _has_filter_params(params):
        form = SchedulerFilter(params)
        cleaned = form.clean() if form.is_valid() else None
        users = _filter_users_on_query(SimpleNamespace(user=request.user), cleaned)
        focus = SchedulerFocus(cleaned)
    else:
        # As the page's unfiltered rows: leavers only on request.
        users = User.objects.filter(
            pk__in=viewable_schedule_user_pks(request.user), is_active=True
        )
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
    users = User.objects.filter(pk__in=users.values("pk"))
    return (users, focus) if with_focus else users


def scoped_schedule(request, policy):
    """The job / phase / project a request's ``job`` / ``phase`` / ``project``
    param names, authorised, as ``(kind, obj)``; ``(None, None)`` if none."""
    from rest_framework.exceptions import NotFound, PermissionDenied

    from ....models import Job, Phase, Project

    for kind, model in (("phase", Phase), ("job", Job), ("project", Project)):
        pk = parse_int_param(request, kind)
        if pk is None:
            continue
        obj = model.objects.filter(pk=pk).first()
        if kind == "project":
            if obj is None or not request.user.has_perm("jobtracker.view_project"):
                raise NotFound()
            return kind, obj
        job = obj.job if kind == "phase" and obj else obj
        if obj is None or not policy.can("job.view", job):
            raise NotFound()
        if not policy.can("job.view_schedule", job):
            raise PermissionDenied("You can't view this job's schedule.")
        return kind, obj
    return None, None


def scoped_schedule_users(request, kind, obj):
    """The people a job / phase / project schedule shows (its team, plus any
    ``include_user`` the caller may see)."""
    from ....utils import merge_include_users
    from ....views.project import _project_scheduled_users

    if kind == "project":
        return _project_scheduled_users(obj)
    team = obj.team_scheduled() if kind == "job" else obj.team()
    return merge_include_users(request._request, team)


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
        users, focus = filtered_schedule_users(request, with_focus=True)
        return Response(
            build_schedule_payload(users, start, end, request=request, focus=focus)
        )

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
        + SCOPE_PARAMS
        + [OpenApiParameter("project", int)]
        + FILTER_PARAMS,
        responses=ScheduleResourcesSerializer,
    )
    @action(detail=False, methods=["get"])
    def resources(self, request):
        kind, obj = scoped_schedule(request, self.policy)
        params = request.query_params
        if params.get("start") or params.get("end"):
            # Validate as every v1 window (400 envelope) and hand the row
            # builder whole days: a date-only end would otherwise mean its
            # midnight and drop that day from utilisation.
            start, end = parse_schedule_window(request)
            query = request._request.GET.copy()
            query["start"], query["end"] = start.isoformat(), end.isoformat()
            request._request.GET = query
        if kind is None:
            rows = scheduler_member_rows(request._request, include_html=False)
        else:
            rows = scheduler_member_rows(
                request._request,
                filtered_users=scoped_schedule_users(request, kind, obj),
                use_filter_form=False,
                role_job=(
                    None if kind == "project" else (obj if kind == "job" else obj.job)
                ),
                role_phase=obj if kind == "phase" else None,
                include_html=False,
            )
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
                    "business_hours": row["businessHours"],
                }
            )
        return Response({"users": out})

    @extend_schema(
        summary="Date extent of the schedule's slots",
        description="Earliest start and latest end among the slots a schedule "
        "would show (for zoom-to-fit). Takes the same filters, or "
        "``job`` / ``phase`` / ``project``.",
        parameters=SCOPE_PARAMS + [OpenApiParameter("project", int)] + FILTER_PARAMS,
        responses=ScheduleBoundsSerializer,
    )
    @action(detail=False, methods=["get"])
    def bounds(self, request):
        from django.db.models import Max, Min

        kind, obj = scoped_schedule(request, self.policy)
        if kind is None:
            slots = TimeSlot.objects.filter(user__in=filtered_schedule_users(request))
        else:
            slots = TimeSlot.objects.filter(
                user__in=scoped_schedule_users(request, kind, obj)
            )
            if kind == "project":
                slots = slots.filter(project=obj)
            elif kind == "phase":
                slots = slots.filter(phase=obj)
            else:
                slots = slots.filter(phase__job=obj)
        agg = slots.aggregate(start=Min("start"), end=Max("end"))
        return Response(ScheduleBoundsSerializer(agg).data)

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
        try:
            since = clean_datetime(request.query_params.get("since"))
        except SuspiciousOperation:
            since = None
        if since is None:
            raise ValidationError({"since": ["Expected an ISO 8601 datetime."]})
        job_id = parse_int_param(request, "job")
        phase_id = parse_int_param(request, "phase")
        # Taken before reading, so nothing committed meanwhile is skipped.
        now = timezone.now()
        limit = 200
        history = schedule_history(
            request.user,
            job_id=job_id,
            phase_id=phase_id,
            limit=limit,
            scan=2000,
            since=since,
        )
        if len(history) >= limit:
            now = history[0].created  # a full page: resume after its last
        # Slots are reloaded in their current state, which may have moved
        # since: only send those of people this view may show.
        from ....models import Job, Phase

        viewable = set(viewable_schedule_user_pks(request.user))
        if phase_id:
            phase = Phase.objects.filter(pk=phase_id).first()
            if phase is not None:
                viewable |= set(phase.team().values_list("pk", flat=True))
        elif job_id:
            job = Job.objects.filter(pk=job_id).first()
            if job is not None:
                viewable |= set(job.team_scheduled().values_list("pk", flat=True))
        deltas = _api_deltas(list(reversed(history)), viewable)
        return Response(
            ScheduleDeltasSerializer({"deltas": deltas, "now": now}).data
        )


def _api_deltas(actions, viewable):
    """The deltas for ``actions`` (oldest first), with every slot and comment
    they touch loaded in one query each (was a pair per action plus lazy
    relations per slot)."""
    parsed = []
    slot_ids, comment_ids = set(), set()
    for action in actions:
        upserted_slots, upserted_comments, removed_slots, removed_comments = (
            [], [], [], []
        )
        for item in action.payload or []:
            is_comment = item["model"] == "timeslotcomment"
            if item["after"] is None:
                (removed_comments if is_comment else removed_slots).append(item["pk"])
            else:
                (upserted_comments if is_comment else upserted_slots).append(
                    item["pk"]
                )
        slot_ids.update(upserted_slots)
        comment_ids.update(upserted_comments)
        parsed.append(
            (action, upserted_slots, upserted_comments, removed_slots, removed_comments)
        )
    slots = {
        s.pk: s
        for s in TimeSlot.objects.filter(
            pk__in=slot_ids, user_id__in=viewable
        ).prefetch_related(
            "phase",
            "phase__job",
            "phase__job__client",
            "project",
            "slot_type",
            "user",
            "leaverequest",
            "rm_inbound__record",
        )
    }
    comments = {
        c.pk: c
        for c in TimeSlotComment.objects.filter(
            pk__in=comment_ids, user_id__in=viewable
        ).select_related("user")
    }
    return [
        {
            "action_id": action.pk,
            "created": action.created,
            "actor_id": action.actor_id,
            "action_type": action.action_type,
            "timeslots": [slots[pk] for pk in up_s if pk in slots],
            "comments": [comments[pk] for pk in up_c if pk in comments],
            "removed_timeslots": rm_s,
            "removed_comments": rm_c,
        }
        for action, up_s, up_c, rm_s, rm_c in parsed
    ]
