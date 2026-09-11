"""Read-only /api/v1/ viewsets.

Every viewset reproduces — never widens — the access checks the existing Django
views apply. Rather than re-deriving the guardian logic, each ``scope_queryset``
delegates to the canonical model managers / helpers so the API cannot drift from
the UI. See the permission section of the implementation plan for the rationale.
"""

from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from guardian.shortcuts import get_objects_for_user
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response

from chaotica_utils.models import User, UserCost
from chaotica_utils.models.job_levels import UserJobLevel
from chaotica_utils.models.leave import LeaveRequest
from chaotica_utils.utils.common import (
    can_manage_user,
    can_manage_job_level,
    can_manage_user_lcr,
)

from ...utils import viewable_schedule_user_pks
from .schedule import (
    SCHEDULE_QUERY_PARAMS,
    build_schedule_payload,
    parse_int_param,
    parse_schedule_window,
)

from ...models import (
    Client,
    Job,
    OrganisationalUnit,
    OrganisationalUnitMember,
    Phase,
    Project,
    Qualification,
    QualificationRecord,
    Service,
    Skill,
    SkillCategory,
    TimeSlot,
    TimeSlotType,
    UserSkill,
)
from .base import BaseReadOnlyAPIViewSet
from .serializers import (
    ClientSerializer,
    JobSerializer,
    LeaveRequestSerializer,
    OrganisationalUnitSerializer,
    OrganisationalUnitMemberSerializer,
    PhaseSerializer,
    ProjectSerializer,
    QualificationRecordSerializer,
    QualificationSerializer,
    ScheduleSerializer,
    ServiceSerializer,
    SkillCategorySerializer,
    SkillSerializer,
    TimeSlotSerializer,
    TimeSlotTypeSerializer,
    UserSerializer,
    UserSkillSerializer,
    UserStatusUpdateSerializer,
    UserProfileUpdateSerializer,
    UserJobLevelUpdateSerializer,
    UserCostUpdateSerializer,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class UserViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = UserSerializer

    # Read verbs + POST — but POST is opened *only* for the set_status action
    # below; create() is overridden to 405 so this is not a user-creation route.
    http_method_names = ["get", "head", "options", "post"]

    def get_base_queryset(self):
        # Prefetch the current job level into ``_current_levels`` so the
        # serializer's get_current_level() fast-path avoids a query per user.
        return User.objects.prefetch_related(
            Prefetch(
                "job_level_history",
                queryset=UserJobLevel.objects.filter(
                    is_current=True
                ).select_related("job_level"),
                to_attr="_current_levels",
            )
        )

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(user, "chaotica_utils.view_user", klass=User)
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))

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
        return Response(
            {"changed": changed, "user": UserSerializer(target).data}
        )

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
        return Response(
            {"changed": changed, "user": UserSerializer(target).data}
        )

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
        effective_from = body.validated_data.get("effective_from") or timezone.now().date()
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
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def get_base_queryset(self):
        return OrganisationalUnit.objects.all()

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(
            user, "jobtracker.view_organisationalunit", klass=OrganisationalUnit
        )
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))

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


class ClientViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ClientSerializer

    def get_base_queryset(self):
        return Client.objects.prefetch_related(
            "account_managers", "tech_account_managers"
        )

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(user, "jobtracker.view_client", klass=Client)
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))


class JobViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = JobSerializer

    def get_base_queryset(self):
        return Job.objects.select_related("unit", "client").annotate(
            phase_count=Count("phases", distinct=True)
        )

    def scope_queryset(self, queryset, user):
        # Faithful to JobPermissionRequiredMixin: unit `can_view_jobs` OR the
        # team-membership guest bypass (jobs_for_user).
        # ``jobs_for_user`` is a ``.distinct()`` queryset while
        # ``jobs_with_unit_permission`` is not; combining a distinct and a
        # non-distinct query with ``|`` raises "Cannot combine a unique query
        # with a non-unique query". Union the pks instead.
        allowed_ids = set(
            Job.objects.jobs_with_unit_permission(
                user, "jobtracker.can_view_jobs"
            ).values_list("pk", flat=True)
        )
        allowed_ids.update(
            Job.objects.jobs_for_user(user).values_list("pk", flat=True)
        )
        return queryset.filter(pk__in=allowed_ids)


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------


class PhaseViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = PhaseSerializer

    def get_base_queryset(self):
        return Phase.objects.select_related(
            "job",
            "service",
            "project_lead",
            "report_author",
            "techqa_by",
            "presqa_by",
        )

    def scope_queryset(self, queryset, user):
        # See JobViewSet: one side is distinct and the other isn't, so union
        # the pks rather than combining the querysets with ``|``.
        allowed_ids = set(
            Phase.objects.phases_with_unit_permission(
                user, "jobtracker.can_view_jobs"
            ).values_list("pk", flat=True)
        )
        allowed_ids.update(
            Phase.objects.phases_for_user(user).values_list("pk", flat=True)
        )
        return queryset.filter(pk__in=allowed_ids)


class ProjectViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ProjectSerializer

    def get_base_queryset(self):
        return Project.objects.select_related("unit", "primary_poc", "created_by")

    def scope_queryset(self, queryset, user):
        # Projects are gated by the ``view_project`` model permission (there is
        # no unit-level project permission), plus the team-membership bypass.
        # get_objects_for_user honours a global grant (returns all) or the
        # per-object grants otherwise, matching ProjectListView.
        allowed_ids = set(
            get_objects_for_user(
                user, "jobtracker.view_project", klass=Project
            ).values_list("pk", flat=True)
        )
        allowed_ids.update(
            Project.objects.projects_for_user(user).values_list("pk", flat=True)
        )
        return queryset.filter(pk__in=allowed_ids)


# ---------------------------------------------------------------------------
# Scheduling
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


class ScheduleViewSet(viewsets.ViewSet):
    """Read-only composite schedule feed for a date window.

    Combines work timeslots, leave, holidays and per-user availability/utilisation
    for every user the requester may see under ``view_users_schedule`` (plus
    themselves). Renders the clean REST shape from the same shared core
    (``jobtracker.utils.collect_schedule_*``) the vis-timeline UI feeds use, so
    the API and the calendar cannot drift. For a single user use the
    ``/users/{id}/schedule/`` action instead.
    """

    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

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


# ---------------------------------------------------------------------------
# People / competency
# ---------------------------------------------------------------------------


class LeaveRequestViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = LeaveRequestSerializer

    def get_base_queryset(self):
        return LeaveRequest.objects.select_related(
            "user", "authorised_by", "timeslot"
        )

    def scope_queryset(self, queryset, user):
        # Exactly the manage_leave visibility clause.
        units = get_objects_for_user(
            user, "can_view_all_leave_requests", klass=OrganisationalUnit
        )
        return queryset.filter(
            Q(user__unit_memberships__unit__in=units)
            | Q(user__manager=user)
            | Q(user__acting_manager=user)
            | Q(user=user)
        ).distinct()


class SkillCategoryViewSet(BaseReadOnlyAPIViewSet):
    """Reference data — visible to all authenticated users."""

    serializer_class = SkillCategorySerializer

    def get_base_queryset(self):
        return SkillCategory.objects.all()


class SkillViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = SkillSerializer

    def get_base_queryset(self):
        return Skill.objects.select_related("category").prefetch_related(
            "prerequisites", "related_skills"
        )

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(user, "jobtracker.view_skill", klass=Skill)
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))


class UserSkillViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = UserSkillSerializer

    def get_base_queryset(self):
        return UserSkill.objects.select_related("skill", "user")

    def scope_queryset(self, queryset, user):
        # Competency data is sensitive. Stricter than the (unenforced) profile
        # view: own records + reports (manager/acting-manager) + holders of the
        # declared view_users_skill permission.
        if user.has_perm("jobtracker.view_users_skill"):
            return queryset
        return queryset.filter(
            Q(user=user)
            | Q(user__manager=user)
            | Q(user__acting_manager=user)
        ).distinct()


class QualificationViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = QualificationSerializer

    def get_base_queryset(self):
        return Qualification.objects.select_related("awarding_body").prefetch_related(
            "tags"
        )

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(
            user, "jobtracker.view_qualification", klass=Qualification
        )
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))


class QualificationRecordViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = QualificationRecordSerializer

    def get_base_queryset(self):
        return QualificationRecord.objects.select_related(
            "qualification", "user", "verified_by"
        )

    def scope_queryset(self, queryset, user):
        if user.has_perm("jobtracker.view_users_qualifications"):
            return queryset
        return queryset.filter(
            Q(user=user)
            | Q(user__manager=user)
            | Q(user__acting_manager=user)
        ).distinct()


class ServiceViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ServiceSerializer

    def get_base_queryset(self):
        return Service.objects.prefetch_related(
            "skillsRequired",
            "skillsDesired",
            "qualificationsRequired",
            "qualificationsDesired",
        )

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(user, "jobtracker.view_service", klass=Service)
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))
