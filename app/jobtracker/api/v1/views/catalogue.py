"""Skills, qualifications and services."""

from guardian.shortcuts import get_objects_for_user



from ....models import (
    Qualification,
    Service,
    Skill,
    SkillCategory,
)
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    QualificationSerializer,
    ServiceSerializer,
    SkillCategorySerializer,
    SkillSerializer,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


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
