"""Phases."""

from rest_framework import serializers


from ....models import (
    Phase,
)


from drf_spectacular.utils import extend_schema_field

from ....selectors.phases import concurrent_phases, phase_missing_billing_code
from ..fields import RefField, RefSerializer, WebUrlField, make_ref
from .jobs import BillingBadgeSerializer, LinkSerializer, WorkflowCapabilitiesMixin


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


class PhaseDetailSerializer(WorkflowCapabilitiesMixin, PhaseSerializer):
    is_delivery_late = serializers.BooleanField(read_only=True)
    is_techqa_late = serializers.BooleanField(source="is_tqa_late", read_only=True)
    is_presqa_late = serializers.BooleanField(source="is_pqa_late", read_only=True)
    is_prechecks_late = serializers.BooleanField(read_only=True)
    scoped_hours = serializers.FloatField(source="get_total_scoped_hours")
    scoped_days = serializers.FloatField(source="get_total_scoped_days")
    scheduled_hours = serializers.FloatField(source="get_total_scheduled_hours")
    scheduled_days = serializers.FloatField(source="get_total_scheduled_days")
    scheduled_pct = serializers.FloatField(source="get_total_scheduled_perc")
    billing = BillingBadgeSerializer(
        source="get_effective_billing_assignments", many=True
    )
    missing_billing_code = serializers.SerializerMethodField()
    concurrent_phases = serializers.SerializerMethodField()
    links = LinkSerializer(many=True)
    deliverable_links = serializers.SerializerMethodField()

    class Meta(PhaseSerializer.Meta):
        fields = PhaseSerializer.Meta.fields + [
            "description",
            "test_target",
            "location",
            "comm_reqs",
            "prerequisites",
            "restrictions",
            "scheduling_requirements",
            "report_to_be_left_on_client_site",
            "pre_checks_done_date",
            "actual_sent_to_tqa_date",
            "actual_sent_to_pqa_date",
            "actual_completed_date",
            "is_delivery_late",
            "is_techqa_late",
            "is_presqa_late",
            "is_prechecks_late",
            "scoped_hours",
            "scoped_days",
            "scheduled_hours",
            "scheduled_days",
            "scheduled_pct",
            "billing",
            "missing_billing_code",
            "concurrent_phases",
            "links",
            "deliverable_links",
            "workflow",
            "capabilities",
        ]

    def get_missing_billing_code(self, phase) -> bool:
        return phase_missing_billing_code(phase)

    @extend_schema_field(RefSerializer(many=True))
    def get_concurrent_phases(self, phase):
        request = self.context.get("request")
        return [make_ref(p, request) for p in concurrent_phases(phase)]

    @extend_schema_field(LinkSerializer(many=True))
    def get_deliverable_links(self, phase):
        out = []
        for title, url in (
            ("Deliverable", phase.linkDeliverable),
            ("Technical data", phase.linkTechData),
            ("Report data", phase.linkReportData),
        ):
            if url:
                out.append({"title": title, "url": url, "type": "Deliverable"})
        return out


class FeedbackItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    type = serializers.IntegerField(source="feedbackType")
    type_display = serializers.CharField(source="get_feedbackType_display")
    author = RefField()
    body = serializers.CharField()
    created_on = serializers.DateTimeField()


class PhaseFeedbackSerializer(serializers.Serializer):
    scope_correct = serializers.BooleanField(
        source="feedback_scope_correct", allow_null=True
    )
    techqa_report_rating = serializers.IntegerField(allow_null=True)
    techqa_report_rating_display = serializers.CharField(
        source="get_techqa_report_rating_display", allow_null=True
    )
    presqa_report_rating = serializers.IntegerField(allow_null=True)
    presqa_report_rating_display = serializers.CharField(
        source="get_presqa_report_rating_display", allow_null=True
    )
    feedback = FeedbackItemSerializer(source="feedback.all", many=True)
