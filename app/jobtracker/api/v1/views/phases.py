"""Phases."""

from ....models import (
    Phase,
)
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    PhaseSerializer,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
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
