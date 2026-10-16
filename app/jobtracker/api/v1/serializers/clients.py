"""Clients."""

from rest_framework import serializers


from ....models import (
    Client,
)


from ..fields import RefListField, WebUrlField


class ClientSerializer(serializers.ModelSerializer):
    is_ready = serializers.BooleanField(source="is_ready_for_jobs", read_only=True)
    account_managers = RefListField()
    tech_account_managers = RefListField()
    web_url = WebUrlField()

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
            "web_url",
        ]
