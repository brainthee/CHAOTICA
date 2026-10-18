"""Skills, qualifications and services."""

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from ....enums import PhaseStatuses
from ....models import (
    AwardingBody,
    Qualification,
    Service,
    Skill,
    SkillCategory,
    UserSkill,
)
from ....selectors.catalogue import (
    matrix_users,
    service_list_with_risk,
    skill_matrix,
    skill_matrix_filter_options,
)
from ....utils import phases_visible_to
from .. import filters
from ..base import BaseReadOnlyAPIViewSet
from ..fields import make_ref
from ..serializers import (
    AwardingBodySerializer,
    PhaseSerializer,
    QualificationDetailSerializer,
    QualificationRecordSerializer,
    QualificationSerializer,
    ServiceCoverageSerializer,
    ServiceListSerializer,
    SkillMatrixSerializer,
    ServiceSerializer,
    SkillCategorySerializer,
    SkillDetailSerializer,
    SkillSerializer,
    UserSkillSerializer,
)

PHASE_BUCKETS = {
    "active": PhaseStatuses.SERVICE_ACTIVE,
    "upcoming": PhaseStatuses.SERVICE_UPCOMING,
    "completed": PhaseStatuses.SERVICE_COMPLETED,
}


class SkillCategoryViewSet(BaseReadOnlyAPIViewSet):
    """Reference data — visible to all authenticated users."""

    serializer_class = SkillCategorySerializer
    policy_scope = None  # reference data
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_base_queryset(self):
        return SkillCategory.objects.all()


class SkillViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = SkillSerializer
    policy_scope = "skill.view"
    filterset_class = filters.SkillFilter
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_serializer_class(self):
        return SkillDetailSerializer if self.action == "retrieve" else SkillSerializer

    def get_base_queryset(self):
        qs = Skill.objects.select_related("category").prefetch_related(
            "prerequisites", "related_skills"
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                "qualifications__awarding_body",
                "services_skill_required",
                "services_skill_desired",
            )
        return qs

    @extend_schema(
        responses=UserSkillSerializer(many=True),
        summary="Who holds this skill",
        description="Ratings of people whose skills you may see (yourself, "
        "your reports, or everyone with view_users_skill).",
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def users(self, request, pk=None):
        skill = self.get_object()
        rows = (
            self.policy.scope(
                "user_skill.view",
                UserSkill.objects.filter(skill=skill, user__is_active=True),
            )
            .select_related("user", "skill")
            .order_by("-rating", "user__last_name")
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(
            UserSkillSerializer(
                page, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("unit", str, description="Org unit slug."),
            OpenApiParameter("team", str, description="Team slug."),
            OpenApiParameter("category", str, description="Skill category slug."),
            OpenApiParameter("role", int, description="Unit role id."),
        ],
        responses=SkillMatrixSerializer,
        summary="Skills matrix",
        description=(
            "``{categories[{category, skills[Ref]}], rows[{user, ratings{skill_id: "
            "{rating, interested}}}], rating_choices, filters}``. Rows cover "
            "only people whose skills you may see."
        ),
    )
    @action(detail=False, methods=["get"], filter_backends=[], pagination_class=None)
    def matrix(self, request):
        q = request.query_params
        users = matrix_users()
        if not request.user.has_perm("jobtracker.view_users_skill"):
            u = request.user
            users = users.filter(Q(pk=u.pk) | Q(manager=u) | Q(acting_manager=u))
        categories, rows = skill_matrix(
            users, q.get("unit"), q.get("team"), q.get("category"), q.get("role")
        )
        from ....enums import UserSkillRatings

        return Response(
            {
                "categories": [
                    {
                        "category": make_ref(cat, request),
                        "skills": [make_ref(sk, request) for sk in cat.skills.all()],
                    }
                    for cat in categories
                ],
                "rows": [
                    {
                        "user": make_ref(row["user"], request),
                        "ratings": {
                            str(skill_id): {
                                "rating": cell["rating"],
                                "interested": cell["interested"],
                            }
                            for skill_id, cell in row["skills"].items()
                        },
                    }
                    for row in rows
                ],
                "rating_choices": [
                    {"value": v, "label": label}
                    for v, label in UserSkillRatings.CHOICES
                ],
                "filters": skill_matrix_filter_options(),
            }
        )


class AwardingBodyViewSet(BaseReadOnlyAPIViewSet):
    """Reference data — visible to all authenticated users."""

    serializer_class = AwardingBodySerializer
    policy_scope = None  # reference data
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_base_queryset(self):
        return AwardingBody.objects.all()


class QualificationViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = QualificationSerializer
    policy_scope = "qualification.view"
    ordering_fields = ("name",)
    search_fields = ("name", "short_name")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return QualificationDetailSerializer
        return QualificationSerializer

    def get_base_queryset(self):
        qs = Qualification.objects.select_related("awarding_body").prefetch_related(
            "tags"
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                "demonstrated_skills__category",
                "services_qual_required",
                "services_qual_desired",
            )
        return qs

    @extend_schema(
        responses=QualificationRecordSerializer(many=True),
        summary="Who holds this qualification",
        description="Records you may see (yourself, your reports, or everyone "
        "with view_users_qualifications).",
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def records(self, request, pk=None):
        qualification = self.get_object()
        rows = (
            self.policy.scope("qualification_record.view", qualification.users.all())
            .select_related("qualification__awarding_body", "user", "verified_by")
            .order_by("-awarded_date")
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(
            QualificationRecordSerializer(
                page, many=True, context=self.get_serializer_context()
            ).data
        )


class ServiceViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ServiceListSerializer
    policy_scope = "service.view"
    filterset_class = filters.ServiceFilter
    ordering_fields = ("name", "risk_score")
    search_fields = ("name",)

    def get_serializer_class(self):
        return ServiceSerializer if self.action == "retrieve" else ServiceListSerializer

    def get_base_queryset(self):
        if self.action == "list":
            return service_list_with_risk().prefetch_related(
                "qualificationsRequired", "qualificationsDesired"
            )
        return Service.objects.prefetch_related(
            "skillsRequired",
            "skillsDesired",
            "qualificationsRequired",
            "qualificationsDesired",
        )

    def _visible_phases(self, service):
        return phases_visible_to(self.request.user, service.phases.all())

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "bucket", str, enum=["all", *PHASE_BUCKETS], description="Default all."
            )
        ],
        responses=PhaseSerializer(many=True),
        summary="This service's phases (on jobs you can see)",
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def phases(self, request, pk=None):
        service = self.get_object()
        bucket = request.query_params.get("bucket", "all")
        if bucket != "all" and bucket not in PHASE_BUCKETS:
            raise ValidationError(
                {"bucket": ["Expected all, active, upcoming or completed."]}
            )
        phases = self._visible_phases(service).select_related(
            "techqa_by", "presqa_by", "job__client"
        )
        if bucket != "all":
            phases = phases.filter(status__in=PHASE_BUCKETS[bucket])
        page = self.paginate_queryset(phases.order_by("-pk"))
        return self.get_paginated_response(
            PhaseSerializer(page, many=True, context=self.get_serializer_context()).data
        )

    @extend_schema(
        responses=OpenApiTypes.OBJECT,
        summary="Delivery metrics and usage",
        description="``{usage, performance}`` — the service page's Jobs and "
        "Performance tabs, over the phases you can see.",
    )
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def metrics(self, request, pk=None):
        service = self.get_object()
        visible = self._visible_phases(service)
        scope = f"user{request.user.pk}"
        return Response(
            {
                "usage": service.get_service_usage_analytics(
                    phases=visible, cache_scope=scope
                ),
                "performance": service.get_performance_metrics(
                    phases=visible, cache_scope=scope
                ),
            }
        )

    @extend_schema(
        responses=ServiceCoverageSerializer,
        summary="Who can deliver this service",
        description=(
            "Counts of people by competency for the required skills, desired-"
            "skill coverage and qualification holders. Named people "
            "(``people``) only with view_users_skill."
        ),
    )
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def coverage(self, request, pk=None):
        service = self.get_object()
        readiness = service.get_service_readiness_breakdown()
        groups = ("specialists", "independent_only", "support_only", "missing_skills")
        named = request.user.has_perm("jobtracker.view_users_skill")
        analysis = service.get_skills_coverage_analysis()

        def skill_rows(rows):
            return [
                {
                    "skill": make_ref(skill, request),
                    **{k: v for k, v in data.items() if k != "training_candidates"},
                    "training_candidates": len(data.get("training_candidates") or []),
                }
                for skill, data in rows.items()
            ]

        quals = list(service.get_users_with_required_quals())
        return Response(
            {
                "counts": {
                    **{g: len(readiness[g]) for g in groups},
                    "total_capable": readiness["total_capable"],
                    "required_quals_holders": len(quals),
                },
                "people": (
                    {
                        **{
                            g: [make_ref(u, request) for u in readiness[g]]
                            for g in groups
                        },
                        "required_quals_holders": [make_ref(u, request) for u in quals],
                    }
                    if named
                    else None
                ),
                "required_skills": skill_rows(analysis["required_skills_analysis"]),
                "desired_skills": skill_rows(analysis["desired_skills_analysis"]),
                "summary": analysis["summary"],
            }
        )
