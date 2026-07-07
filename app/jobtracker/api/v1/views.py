"""Read-only /api/v1/ viewsets.

Every viewset reproduces — never widens — the access checks the existing Django
views apply. Rather than re-deriving the guardian logic, each ``scope_queryset``
delegates to the canonical model managers / helpers so the API cannot drift from
the UI. See the permission section of the implementation plan for the rationale.
"""

from django.db.models import Count, Q
from guardian.shortcuts import get_objects_for_user

from chaotica_utils.models import User
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
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class UserViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = UserSerializer

    def get_base_queryset(self):
        return User.objects.all()

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(user, "chaotica_utils.view_user", klass=User)
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))


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
