"""Sub-resources shared by jobs and phases: notes and activity."""

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action

from chaotica_utils.audit import apply_audit_filters, audit_events_for

from ..serializers import ActivitySerializer, NoteSerializer


class NotesActivityMixin:
    """``/{id}/notes/`` and ``/{id}/activity/``, visible to whoever can see
    the object (the object's own scope applies via ``get_object``)."""

    def _page(self, items, serializer_class):
        page = self.paginate_queryset(items)
        data = serializer_class(
            page, many=True, context=self.get_serializer_context()
        ).data
        return self.get_paginated_response(data)

    @extend_schema(responses=NoteSerializer(many=True), summary="User notes")
    @action(detail=True, methods=["get"], filter_backends=[])
    def notes(self, request, pk=None):
        obj = self.get_object()
        notes = sorted(obj.get_user_notes(), key=lambda n: n.create_date, reverse=True)
        return self._page(notes, NoteSerializer)

    @extend_schema(responses=ActivitySerializer(many=True), summary="Activity log")
    @action(detail=True, methods=["get"], filter_backends=[])
    def activity(self, request, pk=None):
        obj = self.get_object()
        # Sensitive categories are admin-only (audit_events_for), as on the page.
        events = audit_events_for(obj, request.user, limit=None)
        events = apply_audit_filters(events, request.query_params)
        events = events.select_related("actor").order_by("-timestamp", "-pk")
        return self._page(events, ActivitySerializer)
