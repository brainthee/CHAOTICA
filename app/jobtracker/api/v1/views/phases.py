"""Phases."""

from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ....models import Phase
from ....selectors.schedule import phase_team
from .. import filters
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    PhaseDetailSerializer,
    PhaseFeedbackSerializer,
    PhaseSerializer,
    TeamMemberSerializer,
)
from ._engagement import NotesActivityMixin


class PhaseViewSet(NotesActivityMixin, BaseReadOnlyAPIViewSet):
    serializer_class = PhaseSerializer
    policy_scope = "phase.view"
    filterset_class = filters.PhaseFilter
    ordering_fields = (
        "id",
        "phase_number",
        "status",
        "desired_start_date",
        "desired_delivery_date",
        "start_date",
        "delivery_date",
    )
    ordering_aliases = {"start_date": "start_on", "delivery_date": "delivery_on"}
    search_fields = ("title", "phase_id", "job__title")

    def get_serializer_class(self):
        return PhaseDetailSerializer if self.action == "retrieve" else PhaseSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "policy": self.policy}

    def get_base_queryset(self):
        qs = Phase.objects.select_related(
            "job__client",
            "service",
            "project_lead",
            "report_author",
            "techqa_by",
            "presqa_by",
        ).annotate(
            start_on=Coalesce("desired_start_date", "_start_date"),
            delivery_on=Coalesce("desired_delivery_date", "_delivery_date"),
        )
        if self.action == "retrieve":
            qs = qs.select_related("job__unit").prefetch_related(
                "timeslots__user",
                "links",
                "billing_code_assignments__code",
                "job__billing_code_assignments__code",
            )
        return qs

    @extend_schema(responses=TeamMemberSerializer(many=True), summary="Phase team")
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def team(self, request, pk=None):
        phase = self.get_object()
        if not self.policy.can("job.view_schedule", phase.job):
            raise PermissionDenied("You can't view this job's schedule.")
        _labels, entries = phase_team(phase)
        return Response(
            TeamMemberSerializer(
                entries, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(responses=PhaseFeedbackSerializer, summary="QA feedback and ratings")
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def feedback(self, request, pk=None):
        phase = self.get_object()
        phase = Phase.objects.prefetch_related("feedback__author").get(pk=phase.pk)
        return Response(
            PhaseFeedbackSerializer(phase, context=self.get_serializer_context()).data
        )
