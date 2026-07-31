"""Read-only /api/v1/ viewsets.

Every viewset reproduces — never widens — the access checks the existing Django
views apply. Rather than re-deriving the guardian logic, each ``scope_queryset``
delegates to the canonical model managers / helpers so the API cannot drift from
the UI. See the permission section of the implementation plan for the rationale.
"""

from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from guardian.shortcuts import get_objects_for_user
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.response import Response

from chaotica_utils.models import User
from chaotica_utils.models.job_levels import UserJobLevel
from chaotica_utils.models.leave import LeaveRequest

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
    PhaseSerializer,
    ProjectSerializer,
    QualificationRecordSerializer,
    QualificationSerializer,
    ServiceSerializer,
    SkillCategorySerializer,
    SkillSerializer,
    TimeSlotSerializer,
    TimeSlotTypeSerializer,
    UserSerializer,
    UserSkillSerializer,
    UserStatusUpdateSerializer,
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


class OrganisationalUnitViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = OrganisationalUnitSerializer

    def get_base_queryset(self):
        return OrganisationalUnit.objects.all()

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(
            user, "jobtracker.view_organisationalunit", klass=OrganisationalUnit
        )
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))


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
