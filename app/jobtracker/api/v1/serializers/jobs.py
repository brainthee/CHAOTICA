"""Jobs and projects."""

from rest_framework import serializers


from ....models import (
    Job,
    Project,
)


from drf_spectacular.utils import extend_schema_field

from ....selectors.jobs import job_warnings
from ....workflow import workflow_block
from ..fields import RefField, RefListField, WebUrlField


class JobSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    status_colour = serializers.CharField(
        source="status_bs_colour", read_only=True, help_text="Bootstrap colour name."
    )
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
    start_date = serializers.DateField(read_only=True)
    delivery_date = serializers.DateField(read_only=True)
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
            "status_colour",
            "unit",
            "client",
            "account_manager",
            "desired_start_date",
            "desired_delivery_date",
            "start_date",
            "delivery_date",
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


class ContactCardSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    display = serializers.CharField(source="get_full_name")
    job_title = serializers.CharField(source="jobtitle", allow_blank=True)
    email = serializers.EmailField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    mobile = serializers.CharField(allow_blank=True)
    web_url = WebUrlField()


class LinkSerializer(serializers.Serializer):
    title = serializers.CharField()
    url = serializers.CharField(allow_null=True)
    type = serializers.CharField(source="get_linkType_display")


class BillingBadgeSerializer(serializers.Serializer):
    """A billing code as a badge: code and name only, never money."""

    code = serializers.CharField(source="code.code")
    name = serializers.CharField(source="code.name", allow_blank=True)


class WorkflowStepSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    label = serializers.CharField()
    state = serializers.ChoiceField(choices=["done", "current", "todo"])


class WorkflowTransitionSerializer(serializers.Serializer):
    name = serializers.CharField()
    target = serializers.IntegerField()
    label = serializers.CharField()
    style = serializers.CharField()
    icon = serializers.CharField(allow_blank=True)
    menu = serializers.BooleanField()
    needs_reason = serializers.BooleanField()
    ready = serializers.BooleanField()
    allowed = serializers.BooleanField()


class WorkflowSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    status_display = serializers.CharField()
    steps = WorkflowStepSerializer(many=True)
    transitions = WorkflowTransitionSerializer(many=True)


class WorkflowCapabilitiesMixin(serializers.Serializer):
    """``workflow`` and ``capabilities`` from the request's PolicyContext
    (``context["policy"]``)."""

    workflow = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()

    @extend_schema_field(WorkflowSerializer)
    def get_workflow(self, obj):
        return workflow_block(self.context["policy"], obj)

    @extend_schema_field(serializers.DictField(child=serializers.BooleanField()))
    def get_capabilities(self, obj):
        return self.context["policy"].capabilities(obj)


class JobDetailSerializer(WorkflowCapabilitiesMixin, JobSerializer):
    dep_account_manager = RefField()
    created_by = RefField()
    scoped_by = RefListField()
    scoped_signed_off_by = RefField()
    primary_poc = ContactCardSerializer(source="primary_client_poc", allow_null=True)
    contacts = ContactCardSerializer(source="additional_contacts", many=True)
    framework = RefField(source="associated_framework")
    related_jobs = RefListField(source="previous_jobs")
    indicative_services = RefListField()
    links = LinkSerializer(many=True)
    billing = BillingBadgeSerializer(source="get_billing_assignments", many=True)
    warnings = serializers.SerializerMethodField()
    scoped_days = serializers.FloatField(source="get_total_scoped_days")

    class Meta(JobSerializer.Meta):
        fields = JobSerializer.Meta.fields + [
            "overview",
            "is_imported",
            "high_risk",
            "reasons_for_high_risk",
            "technically_complex_test",
            "is_time_limited",
            "retest_included",
            "report_to_third_party",
            "bespoke_project",
            "additional_kit_required",
            "additional_kit_info",
            "kit_sourced_by_client",
            "scoping_requested_on",
            "scoping_completed_date",
            "status_changed_date",
            "dep_account_manager",
            "created_by",
            "scoped_by",
            "scoped_signed_off_by",
            "primary_poc",
            "contacts",
            "framework",
            "related_jobs",
            "indicative_services",
            "links",
            "billing",
            "warnings",
            "scoped_days",
            "workflow",
            "capabilities",
        ]

    def get_warnings(self, job) -> list[str]:
        return job_warnings(job)


class TeamRoleSerializer(serializers.Serializer):
    role = serializers.IntegerField()
    role_display = serializers.CharField(source="role_name")
    hours = serializers.FloatField()
    days = serializers.FloatField()
    confirmed_hours = serializers.FloatField(source="confirmed")
    tentative_hours = serializers.FloatField(source="tentative")


class TeamPhaseRowSerializer(serializers.Serializer):
    phase = RefField()
    assigned_roles = serializers.ListField(child=serializers.CharField())
    roles = TeamRoleSerializer(many=True)
    total_days = serializers.FloatField()
    unscheduled = serializers.BooleanField()


class TeamMemberSerializer(serializers.Serializer):
    user = RefField()
    assigned_roles = serializers.ListField(child=serializers.CharField())
    roles = TeamRoleSerializer(many=True)
    total_hours = serializers.FloatField()
    total_days = serializers.FloatField()
    unscheduled = serializers.BooleanField()
    start = serializers.DateTimeField(allow_null=True)
    end = serializers.DateTimeField(allow_null=True)


class JobTeamMemberSerializer(TeamMemberSerializer):
    phases = TeamPhaseRowSerializer(source="phase_rows", many=True)


class EffortSerializer(serializers.Serializer):
    label = serializers.CharField()
    hours = serializers.FloatField()


class SalesMemberSerializer(serializers.Serializer):
    user = RefField()
    role = serializers.CharField()
    share_percent = serializers.FloatField()
    budget_money = serializers.FloatField(allow_null=True)
    budget_days = serializers.FloatField(allow_null=True)


class JobSalesSerializer(serializers.Serializer):
    """Sales summary. Finance fields are null unless the caller holds
    ``can_view_loaded_costs`` on the job's unit."""

    revenue = serializers.FloatField()
    scoped_days = serializers.FloatField()
    avg_day_rate = serializers.FloatField()
    target_profit = serializers.FloatField()
    effort = EffortSerializer(many=True)
    support_premium = serializers.FloatField()
    staff_cost = serializers.FloatField(allow_null=True)
    profit = serializers.FloatField(allow_null=True)
    profit_perc = serializers.FloatField(allow_null=True)
    meets_target = serializers.BooleanField(allow_null=True)
    support_pool = serializers.FloatField(allow_null=True)
    support_members = SalesMemberSerializer(many=True)
    includes_finance = serializers.BooleanField()


class NoteSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    at = serializers.DateTimeField(source="create_date")
    author = RefField()
    content = serializers.CharField()


class ActivitySerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    at = serializers.DateTimeField(source="timestamp")
    actor = RefField()
    verb = serializers.CharField()
    category = serializers.CharField()
    message = serializers.CharField()


class SupportRoleSerializer(serializers.Serializer):
    """A support-team member on a job. Money and hours budgets are null
    unless the caller holds ``can_view_loaded_costs`` for the job's unit."""

    id = serializers.IntegerField(source="pk")
    user = RefField()
    role = serializers.IntegerField()
    role_display = serializers.CharField(source="get_role_display")
    is_overridden = serializers.BooleanField()
    share_percent = serializers.SerializerMethodField()
    budget_money = serializers.SerializerMethodField()
    budget_hours = serializers.SerializerMethodField()
    drawn_money = serializers.SerializerMethodField()
    remaining_money = serializers.SerializerMethodField()
    remaining_hours = serializers.SerializerMethodField()
    can_cash_out = serializers.BooleanField()

    def _budget(self, role, key, money=True):
        if role.budget is None:
            return None
        if money and not self.context.get("can_view_money"):
            return None
        value = role.budget.get(key)
        return float(value) if value is not None else None

    def get_share_percent(self, role) -> float | None:
        return self._budget(role, "share_percent", money=False)

    def get_budget_money(self, role) -> float | None:
        return self._budget(role, "budget_money")

    def get_budget_hours(self, role) -> float | None:
        return self._budget(role, "budget_hours")

    def get_drawn_money(self, role) -> float | None:
        return self._budget(role, "drawn_money")

    def get_remaining_money(self, role) -> float | None:
        return self._budget(role, "remaining_money")

    def get_remaining_hours(self, role) -> float | None:
        return self._budget(role, "remaining_hours")
