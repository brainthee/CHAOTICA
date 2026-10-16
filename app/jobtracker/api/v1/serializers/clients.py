"""Clients."""

from rest_framework import serializers


from ....models import (
    Client,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class ClientSerializer(serializers.ModelSerializer):
    is_ready = serializers.BooleanField(source="is_ready_for_jobs", read_only=True)
    account_managers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    tech_account_managers = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )

    class Meta:
        model = Client
        # jobs_count intentionally omitted: the client detail view re-gates the
        # client's jobs per-object, so a raw count would leak jobs the viewer
        # cannot see.
        fields = [
            "id",
            "name",
            "slug",
            "is_ready",
            "account_managers",
            "tech_account_managers",
        ]
