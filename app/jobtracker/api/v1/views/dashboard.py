"""Dashboard, alarms, entropy and notifications for the caller."""

from constance import config
from django.http import Http404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response

from chaotica_utils.views.entropy import compute_entropy
from notifications import selectors as notes

from ....selectors.dashboard import (
    DashboardScope,
    alarm_groups,
    dashboard_queues,
    dashboard_stats,
    team_utilisation,
)
from ..base import ApiView
from ..serializers import (
    AlarmsSerializer,
    DashboardSerializer,
    MarkReadSerializer,
    NotificationSerializer,
    UpdatedCountSerializer,
)
from ..pagination import StandardResultsPagination


class MeDashboardView(ApiView):
    """The dashboard's first paint: which queues the caller has (with
    counts), alarm counts, their stats and their primary unit's utilisation."""

    @extend_schema(responses=DashboardSerializer, summary="My dashboard")
    def get(self, request):
        today = timezone.now().date()
        scope = DashboardScope(request.user, self.policy, today)
        unit, team = team_utilisation(request.user, today)
        if unit is not None and unit.pk not in self.policy.unit_ids(
            "jobtracker.view_users_schedule"
        ):
            team = []  # utilisation is schedule data
        data = {
            "queues": dashboard_queues(scope),
            "alarm_counts": alarm_groups(scope)["counts"],
            "stats": dashboard_stats(request.user, today),
            "team_unit": unit,
            "team": team,
            "capabilities": self.policy.global_capabilities(),
        }
        return Response(DashboardSerializer(data, context={"request": request}).data)


class MeAlarmsView(ApiView):
    @extend_schema(responses=AlarmsSerializer, summary="My alarms")
    def get(self, request):
        scope = DashboardScope(request.user, self.policy)
        return Response(
            AlarmsSerializer(alarm_groups(scope), context={"request": request}).data
        )


class EntropyView(ApiView):
    @extend_schema(
        summary="Entropy meter (404 when the feature is off)",
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        if not config.ENTROPY_METER_ENABLED:
            raise Http404
        return Response(compute_entropy(request.user, self.policy))


class NotificationListView(ApiView):
    @extend_schema(
        parameters=[OpenApiParameter("unread_only", bool)],
        responses=NotificationSerializer(many=True),
        summary="My notifications",
    )
    def get(self, request):
        unread_only = request.query_params.get("unread_only", "").lower() in (
            "1",
            "true",
        )
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(
            notes.notifications_for(request.user, unread_only), request, view=self
        )
        rows = [notes.serialize_notification(n) for n in page]
        return paginator.get_paginated_response(
            NotificationSerializer(rows, many=True).data
        )


class NotificationUnreadCountView(ApiView):
    @extend_schema(responses=UpdatedCountSerializer, summary="Unread count")
    def get(self, request):
        return Response(
            {"updated": 0, "unread_count": notes.unread_count(request.user)}
        )


class NotificationMarkReadView(ApiView):
    @extend_schema(
        request=MarkReadSerializer,
        responses=UpdatedCountSerializer,
        summary="Mark notifications read or unread",
    )
    def post(self, request):
        body = MarkReadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        updated = notes.set_read(
            request.user, body.validated_data["ids"], body.validated_data["read"]
        )
        return Response(
            {"updated": updated, "unread_count": notes.unread_count(request.user)}
        )


class NotificationMarkAllReadView(ApiView):
    @extend_schema(
        request=None, responses=UpdatedCountSerializer, summary="Mark all read"
    )
    def post(self, request):
        updated = notes.mark_all_read(request.user)
        return Response({"updated": updated, "unread_count": 0})
