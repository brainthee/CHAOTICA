"""DataTables API for the Activity Log (AuditEvent).

Follows the project's legacy ``/api/`` server-side DataTables idiom: a read-only
DRF viewset returning pre-rendered HTML columns, consumed with
``?format=datatables``. Admin-only, matching the Activity Log page. Registered on
the jobtracker router (the shared ``/api/`` mount).
"""

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils.html import format_html
from rest_framework import serializers, viewsets, permissions

from .models import AuditEvent, SENSITIVE_CATEGORIES
from .audit import user_is_global_admin, apply_audit_filters


class IsGlobalAdmin(permissions.BasePermission):
    message = "Only global administrators may view the activity log."

    def has_permission(self, request, view):
        return user_is_global_admin(request.user)


class AuditEventSerializer(serializers.ModelSerializer):
    timestamp_display = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()
    verb_display = serializers.SerializerMethodField()
    actor_display = serializers.SerializerMethodField()
    target_display = serializers.SerializerMethodField()
    source_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "timestamp_display",
            "category_display",
            "verb_display",
            "actor_display",
            "target_display",
            "source_display",
            "message",
        ]
        datatables_always_serialize = ("id",)

    def get_timestamp_display(self, obj):
        return format_html(
            '<span data-bs-toggle="tooltip" title="{}">{}</span>',
            obj.timestamp,
            naturaltime(obj.timestamp),
        )

    def get_category_display(self, obj):
        colour = "warning" if obj.category in SENSITIVE_CATEGORIES else "secondary"
        return format_html(
            '<span class="badge badge-phoenix badge-phoenix-{}">{}</span>',
            colour,
            obj.get_category_display(),
        )

    def get_verb_display(self, obj):
        return obj.get_verb_display()

    def get_actor_display(self, obj):
        if obj.actor_id is None:
            return format_html('<span class="fw-semi-bold">SYSTEM</span>')
        label = obj.actor_repr or str(obj.actor)
        url = getattr(obj.actor, "get_absolute_url", None)
        if callable(url):
            return format_html('<a href="{}">{}</a>', url(), label)
        return format_html("{}", label)

    def get_target_display(self, obj):
        label = obj.target_repr or (str(obj.target) if obj.target else "—")
        target = obj.target
        url = getattr(target, "get_absolute_url", None) if target else None
        if callable(url):
            return format_html('<a href="{}">{}</a>', url(), label)
        return format_html("{}", label)

    def get_source_display(self, obj):
        return obj.get_source_display()


class AuditEventViewSet(viewsets.ModelViewSet):
    serializer_class = AuditEventSerializer
    permission_classes = [permissions.IsAuthenticated, IsGlobalAdmin]
    http_method_names = ["get", "head"]

    def get_queryset(self):
        qs = AuditEvent.objects.select_related(
            "actor", "target_content_type"
        ).all()
        return apply_audit_filters(qs, self.request.query_params)
