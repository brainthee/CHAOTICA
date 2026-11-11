"""Scoping templates (questionnaires) + the scope calculator (#557).

Exposes the data-driven scoping engine over /api/v1/ so LCARS and scripts can
fetch a questionnaire and score a scope without the web form.
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from ....models.scoping import ScopingTemplate
from ....scoping_engine import evaluate
from ..base import ApiView, BaseReadOnlyAPIViewSet
from ..serializers import (
    ScopingCalcInputSerializer,
    ScopingCalcResultSerializer,
    ScopingTemplateSerializer,
)


class ScopingTemplateViewSet(BaseReadOnlyAPIViewSet):
    """Active scoping templates with their fields/options.

    Reference data: the questionnaires are not job/client specific, so any
    authenticated user may read them to build a scoping UI or script.
    """

    serializer_class = ScopingTemplateSerializer
    policy_scope = None  # reference data
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_base_queryset(self):
        return ScopingTemplate.objects.filter(is_active=True).prefetch_related("fields")


class ScopingCalculateView(ApiView):
    """Score a scope against a template without persisting anything."""

    @extend_schema(
        request=ScopingCalcInputSerializer,
        responses=ScopingCalcResultSerializer,
        summary="Calculate a scope",
        description=(
            "POST ``{template: <id|slug>, answers: {slug: value}}``. Returns "
            "testing/reporting days, delivery/reporting hours, a justification "
            "and any calculation errors."
        ),
    )
    def post(self, request):
        body = ScopingCalcInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        ref = str(body.validated_data["template"])
        if ref.isdigit():
            template = get_object_or_404(
                ScopingTemplate, pk=int(ref), is_active=True
            )
        else:
            template = get_object_or_404(
                ScopingTemplate, slug=ref, is_active=True
            )
        result = evaluate(template, body.validated_data.get("answers") or {})
        return Response(ScopingCalcResultSerializer(result).data)
