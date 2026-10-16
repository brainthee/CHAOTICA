"""Phases."""

from ....models import (
    Phase,
)
from .. import filters
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    PhaseSerializer,
)


class PhaseViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = PhaseSerializer
    policy_scope = "phase.view"
    filterset_class = filters.PhaseFilter
    ordering_fields = (
        "id",
        "phase_number",
        "status",
        "desired_start_date",
        "desired_delivery_date",
    )
    search_fields = ("title", "phase_id", "job__title")

    def get_base_queryset(self):
        return Phase.objects.select_related(
            "job__client",
            "service",
            "project_lead",
            "report_author",
            "techqa_by",
            "presqa_by",
        )
