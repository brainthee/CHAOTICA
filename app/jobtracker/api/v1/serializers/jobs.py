"""Jobs and projects."""

from rest_framework import serializers


from ....models import (
    Job,
    Project,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class JobSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    restricted_detail_display = serializers.CharField(
        source="get_restricted_detail_display", read_only=True
    )
    # Annotated in the viewset's get_base_queryset.
    phase_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "slug",
            "external_id",
            "title",
            "status",
            "status_display",
            "unit",
            "unit_name",
            "client",
            "client_name",
            "desired_start_date",
            "desired_delivery_date",
            "is_restricted",
            "restricted_detail",
            "restricted_detail_display",
            "phase_count",
        ]


class ProjectSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    is_tracked = serializers.BooleanField(read_only=True)
    # start_date / delivery_date are methods that fall back to the schedule.
    start_date = serializers.DateField(read_only=True)
    delivery_date = serializers.DateField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "slug",
            "external_id",
            "title",
            "status",
            "status_display",
            "unit",
            "unit_name",
            "primary_poc",
            "created_by",
            "desired_start_date",
            "desired_delivery_date",
            "start_date",
            "delivery_date",
            "overview",
            "is_tracked",
        ]
