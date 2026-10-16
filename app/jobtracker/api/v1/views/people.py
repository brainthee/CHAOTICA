"""Users, org units, leave and competency records."""

from django.db.models import Exists, OuterRef, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.response import Response

from chaotica_utils.models import User, UserCost
from chaotica_utils.models.job_levels import UserJobLevel
from chaotica_utils.models.leave import LeaveRequest
from chaotica_utils.utils.common import (
    can_manage_user,
    can_manage_job_level,
    can_manage_user_lcr,
)

from ....enums import DefaultTimeSlotTypes
from ....utils import viewable_schedule_user_pks
from ..schedule import (
    SCHEDULE_QUERY_PARAMS,
    build_schedule_payload,
    parse_schedule_window,
)

from ....models import (
    OrganisationalUnit,
    OrganisationalUnitMember,
    QualificationRecord,
    UserSkill,
    TimeSlot,
)
from .. import filters
from ..base import BaseReadOnlyAPIViewSet
from ....selectors.dashboard import user_stats
from ..serializers import (
    UserStatsSerializer,
    LeaveRequestListSerializer,
    LeaveRequestSerializer,
    OrganisationalUnitSerializer,
    OrganisationalUnitMemberSerializer,
    QualificationRecordSerializer,
    ScheduleSerializer,
    UserSerializer,
    UserSkillSerializer,
    UserStatusUpdateSerializer,
    UserProfileUpdateSerializer,
    UserJobLevelUpdateSerializer,
    UserCostUpdateSerializer,
)


class UserViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = UserSerializer
    policy_scope = "user.view"
    filterset_class = filters.UserFilter
    ordering_fields = ("last_name", "first_name", "email")
    search_fields = ("first_name", "last_name", "email")

    # Read verbs + POST — but POST is opened *only* for the set_status action
    # below; create() is overridden to 405 so this is not a user-creation route.
    http_method_names = ["get", "head", "options", "post"]

    def get_base_queryset(self):
        # Prefetch the current job level into ``_current_levels`` so the
        # serializer's get_current_level() fast-path avoids a query per user.
        return User.objects.select_related("city").prefetch_related(
            Prefetch(
                "job_level_history",
                queryset=UserJobLevel.objects.filter(is_current=True).select_related(
                    "job_level"
                ),
                to_attr="_current_levels",
            )
        )

    def create(self, request, *args, **kwargs):
        # POST is enabled on this viewset only for set_status; the router still
        # maps POST /users/ to create(), so block it explicitly.
        raise MethodNotAllowed("POST")

    @extend_schema(
        request=UserStatusUpdateSerializer,
        responses=UserSerializer,
        description=(
            "Activate or deactivate a user account. Requires the "
            "``chaotica_utils.manage_user`` permission. Deactivation also closes "
            "the user's open team and org-unit memberships. Idempotent."
        ),
    )
    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        """Set a user's active status — the API twin of the ``user_manage_status``
        management view, gated on the same ``manage_user`` permission."""
        if not request.user.has_perm("chaotica_utils.manage_user"):
            raise PermissionDenied(
                "You need the 'manage_user' permission to change account status."
            )

        body = UserStatusUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        target_active = body.validated_data["is_active"]

        # Looked up from the full table (not the view-scoped queryset): the
        # management action is gated on manage_user, not view_user, and we
        # reproduce that gate rather than widen or narrow it.
        target = get_object_or_404(User, pk=pk)

        # Footgun guard: don't let a caller lock themselves out of the app.
        if not target_active and target == request.user:
            raise PermissionDenied("You cannot deactivate your own account.")

        changed = target.set_active_status(target_active)
        return Response({"changed": changed, "user": UserSerializer(target).data})

    @extend_schema(
        request=UserProfileUpdateSerializer,
        responses=UserSerializer,
        description=(
            "Partially update a user's org-chart profile (first/last name, "
            "job title, city, country). Reproduces the gate on the "
            "``update_profile`` UI view: the caller must be the user themselves, "
            "their (acting) manager, or hold ``chaotica_utils.manage_user``. "
            "Does not touch account status, cost rates or job level (those have "
            "their own actions)."
        ),
    )
    @action(detail=True, methods=["post"], url_path="update-profile")
    def update_profile(self, request, pk=None):
        # Full-table lookup: the gate is can_manage_user, not the view_user
        # scope this viewset lists by. Reproduce, don't widen.
        target = get_object_or_404(User, pk=pk)
        if not can_manage_user(request.user, target):
            raise PermissionDenied("You do not have permission to manage this user.")

        body = UserProfileUpdateSerializer(target, data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        city_changed = "city" in body.validated_data
        user = body.save()
        user.profile_last_updated = timezone.now().date()
        user.save(update_fields=["profile_last_updated"])
        # Keep cached lat/long in step with a city change (mirrors update_profile).
        if city_changed and hasattr(user, "update_latlong"):
            user.update_latlong()
        return Response(UserSerializer(user).data)

    @extend_schema(
        request=UserJobLevelUpdateSerializer,
        responses=UserSerializer,
        description=(
            "Set or clear a user's current career level (by short label, e.g. "
            "``JL5``). Effective-dated and idempotent: a new assignment is only "
            "created when the level actually changes, dated ``effective_from`` "
            "(default today), and the prior assignment is closed off "
            "(is_current=False) — so re-running an unchanged import is a no-op. "
            "Reproduces the UI's job-level gate: the caller must be the user's "
            "(acting) manager, a superuser/staff, or the user themselves when "
            "they have no manager."
        ),
    )
    @action(detail=True, methods=["post"], url_path="set-job-level")
    def set_job_level(self, request, pk=None):
        target = get_object_or_404(User, pk=pk)
        if not can_manage_job_level(request.user, target):
            raise PermissionDenied(
                "You do not have permission to manage this user's job level."
            )

        body = UserJobLevelUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        current = UserJobLevel.get_current_level(target)
        changed = False

        if body.validated_data["clear"]:
            if current:
                current.is_current = False
                current.save()
                changed = True
        else:
            job_level = body.validated_data["job_level_obj"]
            # Diff: only create (and close off the old) when the level changes.
            if not current or current.job_level_id != job_level.id:
                UserJobLevel.assign_level(
                    user=target,
                    job_level=job_level,
                    assigned_date=body.validated_data.get("effective_from"),
                    notes=body.validated_data.get("notes", ""),
                )
                changed = True
        return Response({"changed": changed, "user": UserSerializer(target).data})

    @extend_schema(
        request=UserCostUpdateSerializer,
        responses=None,
        description=(
            "Set a user's date-effective loaded cost rate (LCR). Effective-dated "
            "and idempotent: if the rate in force on ``effective_from`` (default "
            "today) already equals the posted value, nothing is written "
            "(``changed=false``); otherwise a new row is added at that date and "
            "the previous rate is superseded from then on. So a weekly import "
            "only ever adds a row when the number actually moves. Gated on the "
            "``jobtracker.can_view_loaded_costs`` finance permission — held "
            "globally, or on every org-unit the target belongs to."
        ),
    )
    @action(detail=True, methods=["post"], url_path="set-cost")
    def set_cost(self, request, pk=None):
        target = get_object_or_404(User, pk=pk)
        if not can_manage_user_lcr(request.user, target):
            raise PermissionDenied(
                "You need the 'can_view_loaded_costs' finance permission for "
                "this user to set their loaded cost rate."
            )

        body = UserCostUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        effective_from = (
            body.validated_data.get("effective_from") or timezone.now().date()
        )
        new_cost = body.validated_data["cost_per_hour"]

        # Diff against the rate already effective on that date. If unchanged,
        # don't clutter the history with a redundant row.
        current = UserCost.cost_on(target, effective_from)
        if current is not None and current == new_cost:
            return Response(
                {
                    "changed": False,
                    "created": False,
                    "user_id": target.id,
                    "effective_from": effective_from,
                    "cost_per_hour": str(new_cost),
                }
            )

        cost, created = UserCost.objects.update_or_create(
            user=target,
            effective_from=effective_from,
            defaults={"cost_per_hour": new_cost},
        )
        return Response(
            {
                "changed": True,
                "created": created,
                "user_id": target.id,
                "effective_from": cost.effective_from,
                "cost_per_hour": str(cost.cost_per_hour),
            }
        )

    @extend_schema(
        summary="A user's consultant stats and QA ratings",
        description=(
            "Visible to the user, their (acting) manager and holders of "
            "``manage_user`` (``User.can_be_managed_by``)."
        ),
        responses=UserStatsSerializer,
    )
    @action(detail=True, methods=["get"], url_path="stats")
    def stats(self, request, pk=None):
        target = get_object_or_404(User, pk=pk)
        if not target.can_be_managed_by(request.user):
            raise PermissionDenied("You can't view this user's stats.")
        return Response(UserStatsSerializer(user_stats(target)).data)

    @extend_schema(
        summary="A single user's schedule window",
        description=(
            "Composite schedule (timeslots, leave, holidays, availability) for "
            "one user over a date window. Authorised by schedule visibility "
            "(``view_users_schedule`` on a shared org unit, or the user "
            "themselves) — not the ``view_user`` list scope — mirroring the "
            "scheduler feeds. See ``/schedule/`` for all visible users."
        ),
        parameters=SCHEDULE_QUERY_PARAMS,
        responses=ScheduleSerializer,
    )
    @action(detail=True, methods=["get"], url_path="schedule")
    def schedule(self, request, pk=None):
        # Gate on schedule visibility, not the view_user list queryset: a caller
        # may legitimately see a user's schedule without appearing in view_user.
        # (pk is guaranteed numeric by lookup_value_regex; the visible-pks set
        # only ever contains real users, so a permission-first check is both
        # sufficient and avoids leaking existence via a 404-vs-403 distinction.)
        if int(pk) not in viewable_schedule_user_pks(request.user):
            raise PermissionDenied(
                "You do not have permission to view this user's schedule."
            )
        # A queryset, not an instance — the utilisation engine needs .values_list.
        users = User.objects.filter(pk=pk)
        start, end = parse_schedule_window(request)
        return Response(build_schedule_payload(users, start, end))


class OrganisationalUnitViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = OrganisationalUnitSerializer
    policy_scope = "org_unit.view"
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_base_queryset(self):
        return OrganisationalUnit.objects.all()

    @extend_schema(
        summary="List members of an org unit",
        description=(
            "Returns all current members of the org unit (active and inactive). "
            "Scoped to org units the requesting user has ``view_organisationalunit`` "
            "permission on."
        ),
        parameters=[
            OpenApiParameter(
                "include_inactive",
                OpenApiTypes.BOOL,
                OpenApiParameter.QUERY,
                description="When true, include members whose account is inactive (default: false).",
                required=False,
            )
        ],
    )
    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        unit = get_object_or_404(self.get_queryset(), pk=pk)
        # Annotate is_lead from the unit's leads M2M so we don't hit the DB
        # once per member.
        lead_subquery = OrganisationalUnit.leads.through.objects.filter(
            organisationalunit_id=unit.pk,
            user_id=OuterRef("member_id"),
        )
        memberships = (
            # left_date__isnull=True — "current members" only, matching every
            # other current-member query in the codebase (orgunit.py). Someone
            # who has left the unit is not a member regardless of is_active.
            OrganisationalUnitMember.objects.filter(unit=unit, left_date__isnull=True)
            .select_related("member")
            .prefetch_related("roles")
            .annotate(is_lead=Exists(lead_subquery))
            .order_by("member__last_name", "member__first_name")
        )
        include_inactive = request.query_params.get("include_inactive", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if not include_inactive:
            memberships = memberships.filter(member__is_active=True)
        serializer = OrganisationalUnitMemberSerializer(memberships, many=True)
        return Response(serializer.data)


class LeaveRequestViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = LeaveRequestListSerializer
    policy_scope = "leave.view"
    filterset_class = filters.LeaveRequestFilter
    ordering_fields = ("start_date", "requested_on")

    def get_base_queryset(self):
        overlap = TimeSlot.objects.filter(
            user=OuterRef("user"),
            slot_type=DefaultTimeSlotTypes.DELIVERY,
            start__lte=OuterRef("end_date"),
            end__gte=OuterRef("start_date"),
        )
        return LeaveRequest.objects.select_related(
            "user__manager", "user__acting_manager", "authorised_by", "timeslot"
        ).annotate(overlaps_work_ann=Exists(overlap))


class UserSkillViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = UserSkillSerializer
    policy_scope = "user_skill.view"

    def get_base_queryset(self):
        return UserSkill.objects.select_related("skill", "user")


class QualificationRecordViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = QualificationRecordSerializer
    policy_scope = "qualification_record.view"

    def get_base_queryset(self):
        return QualificationRecord.objects.select_related(
            "qualification__awarding_body", "user", "verified_by"
        )
