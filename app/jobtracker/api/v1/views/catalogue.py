"""Skills, qualifications and services."""

from ....models import (
    Qualification,
    Service,
    Skill,
    SkillCategory,
)
from .. import filters
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    QualificationSerializer,
    ServiceSerializer,
    SkillCategorySerializer,
    SkillSerializer,
)


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

    def get_base_queryset(self):
        return Skill.objects.select_related("category").prefetch_related(
            "prerequisites", "related_skills"
        )


class QualificationViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = QualificationSerializer
    policy_scope = "qualification.view"
    ordering_fields = ("name",)
    search_fields = ("name", "short_name")

    def get_base_queryset(self):
        return Qualification.objects.select_related("awarding_body").prefetch_related(
            "tags"
        )


class ServiceViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ServiceSerializer
    policy_scope = "service.view"
    filterset_class = filters.ServiceFilter
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_base_queryset(self):
        return Service.objects.prefetch_related(
            "skillsRequired",
            "skillsDesired",
            "qualificationsRequired",
            "qualificationsDesired",
        )
