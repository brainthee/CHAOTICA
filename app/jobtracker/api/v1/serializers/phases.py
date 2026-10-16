"""Phases."""

from rest_framework import serializers


from ....models import (
    Phase,
)


from ..fields import RefField, WebUrlField


class PhaseSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    job = RefField()
    client = RefField(source="job.client")
    service = RefField()
    project_lead = RefField()
    report_author = RefField()
    techqa_by = RefField()
    presqa_by = RefField()
    web_url = WebUrlField()
    # Computed date properties (may be None).
    start_date = serializers.DateField(read_only=True)
    delivery_date = serializers.DateField(read_only=True)
    due_to_techqa = serializers.DateField(read_only=True)
    due_to_presqa = serializers.DateField(read_only=True)

    class Meta:
        model = Phase
        fields = [
            "id",
            "phase_id",
            "slug",
            "phase_number",
            "title",
            "status",
            "status_display",
            "job",
            "client",
            "service",
            "project_lead",
            "report_author",
            "techqa_by",
            "presqa_by",
            "start_date",
            "delivery_date",
            "due_to_techqa",
            "due_to_presqa",
            "desired_start_date",
            "desired_delivery_date",
            "actual_start_date",
            "actual_delivery_date",
            "number_of_reports",
            "is_testing_onsite",
            "is_reporting_onsite",
            "delivery_hours",
            "reporting_hours",
            "mgmt_hours",
            "qa_hours",
            "oversight_hours",
            "debrief_hours",
            "contingency_hours",
            "other_hours",
            "web_url",
        ]
