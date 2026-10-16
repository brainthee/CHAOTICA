"""Jobs and projects."""

from rest_framework import serializers


from ....models import (
    Job,
    Project,
)


from ..fields import RefField, WebUrlField


class JobSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    # ``id`` is the primary key (what /jobs/{id}/ and refs use); the Job ID
    # people quote is ``job_id``.
    id = serializers.IntegerField(source="pk", read_only=True)
    job_id = serializers.IntegerField(source="id", read_only=True)
    unit = RefField()
    client = RefField()
    account_manager = RefField()
    web_url = WebUrlField()
    restricted_detail_display = serializers.CharField(
        source="get_restricted_detail_display", read_only=True
    )
    # Annotated in the viewset's get_base_queryset.
    phase_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "job_id",
            "slug",
            "external_id",
            "title",
            "status",
            "status_display",
            "unit",
            "client",
            "account_manager",
            "desired_start_date",
            "desired_delivery_date",
            "is_restricted",
            "restricted_detail",
            "restricted_detail_display",
            "phase_count",
            "web_url",
        ]


class ProjectSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    id = serializers.IntegerField(source="pk", read_only=True)
    project_id = serializers.IntegerField(source="id", read_only=True)
    unit = RefField()
    primary_poc = RefField()
    created_by = RefField()
    web_url = WebUrlField()
    is_tracked = serializers.BooleanField(read_only=True)
    # start_date / delivery_date are methods that fall back to the schedule.
    start_date = serializers.DateField(read_only=True)
    delivery_date = serializers.DateField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "project_id",
            "slug",
            "external_id",
            "title",
            "status",
            "status_display",
            "unit",
            "primary_poc",
            "created_by",
            "desired_start_date",
            "desired_delivery_date",
            "start_date",
            "delivery_date",
            "overview",
            "is_tracked",
            "web_url",
        ]
