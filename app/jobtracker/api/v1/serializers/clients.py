"""Clients."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from ....models import Client, Contact, FrameworkAgreement
from ....selectors.clients import framework_usage
from ..fields import RefField, RefListField, RefSerializer, WebUrlField, make_ref


class ClientSerializer(serializers.ModelSerializer):
    is_ready = serializers.BooleanField(source="is_ready_for_jobs", read_only=True)
    # Counts of the client's jobs / projects *you* can see (annotated on lists).
    jobs_count = serializers.IntegerField(read_only=True, required=False)
    projects_count = serializers.IntegerField(read_only=True, required=False)
    account_managers = RefListField()
    tech_account_managers = RefListField()
    web_url = WebUrlField()

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "slug",
            "is_ready",
            "account_managers",
            "tech_account_managers",
            "jobs_count",
            "projects_count",
            "web_url",
        ]


class ClientDetailSerializer(ClientSerializer):
    contacts = serializers.SerializerMethodField()
    frameworks = serializers.SerializerMethodField()

    class Meta(ClientSerializer.Meta):
        fields = ClientSerializer.Meta.fields + [
            "short_name",
            "external_id",
            "hours_in_day",
            "specific_requirements",
            "specific_reporting_requirements",
            "onboarding_required",
            "onboarding_requirements",
            "contacts",
            "frameworks",
        ]

    @extend_schema_field(RefSerializer(many=True))
    def get_contacts(self, client):
        # Contact details need view_contact (as on the client page).
        if not self.context["policy"].user.has_perm("jobtracker.view_contact"):
            return []
        request = self.context.get("request")
        return [make_ref(c, request) for c in client.contacts.all()]

    @extend_schema_field(RefSerializer(many=True))
    def get_frameworks(self, client):
        if not self.context["policy"].user.has_perm(
            "jobtracker.view_frameworkagreement"
        ):
            return []
        request = self.context.get("request")
        return [make_ref(f, request) for f in client.framework_agreements.all()]


class ContactSerializer(serializers.ModelSerializer):
    display = serializers.CharField(source="get_full_name", read_only=True)
    client = RefField(source="company")
    web_url = WebUrlField()

    class Meta:
        model = Contact
        fields = [
            "id",
            "display",
            "salutation",
            "first_name",
            "last_name",
            "jobtitle",
            "department",
            "email",
            "phone",
            "mobile",
            "client",
            "web_url",
        ]


class FrameworkSerializer(serializers.ModelSerializer):
    client = RefField()
    web_url = WebUrlField()

    class Meta:
        model = FrameworkAgreement
        fields = [
            "id",
            "name",
            "client",
            "start_date",
            "end_date",
            "total_days",
            "allow_over_allocation",
            "closed",
            "web_url",
        ]


class _Days(serializers.Serializer):
    used_days = serializers.FloatField()
    scheduled_days = serializers.FloatField()
    total_days = serializers.FloatField()


class UsagePhaseSerializer(_Days):
    phase = RefSerializer()


class UsageJobSerializer(_Days):
    job = RefSerializer()
    phases = UsagePhaseSerializer(many=True)


class UsagePersonSerializer(_Days):
    user = RefSerializer()


class UsageRoleSerializer(_Days):
    role = serializers.CharField()


class UsageServiceSerializer(_Days):
    service = RefSerializer()


class UsageMonthSerializer(serializers.Serializer):
    month = serializers.CharField(help_text="YYYY-MM")
    days = serializers.FloatField()
    cumulative = serializers.FloatField()


class FrameworkUsageSerializer(serializers.Serializer):
    days_used = serializers.FloatField()
    days_scheduled = serializers.FloatField()
    days_available = serializers.FloatField()
    over_allocated = serializers.BooleanField()
    jobs = UsageJobSerializer(many=True)
    people = UsagePersonSerializer(many=True)
    roles = UsageRoleSerializer(many=True)
    services = UsageServiceSerializer(many=True)
    monthly = UsageMonthSerializer(many=True)


class FrameworkDetailSerializer(FrameworkSerializer):
    """Usage: days used / scheduled / left, by job (and phase), person, role,
    service and month — the framework page's figures."""

    usage = serializers.SerializerMethodField()

    class Meta(FrameworkSerializer.Meta):
        fields = FrameworkSerializer.Meta.fields + ["usage"]

    @extend_schema_field(FrameworkUsageSerializer)
    def get_usage(self, fw):
        request = self.context.get("request")
        u = framework_usage(fw)

        def days(row):
            return {
                k: float(row[k]) for k in ("used_days", "scheduled_days", "total_days")
            }

        return {
            "days_used": float(fw.computed_days_used),
            "days_scheduled": float(fw.computed_days_scheduled),
            "days_available": float(fw.computed_days_available),
            "over_allocated": fw.computed_is_over_allocated,
            "jobs": [
                {
                    "job": make_ref(j["job"], request),
                    **days(j),
                    "phases": [
                        {"phase": make_ref(p["phase"], request), **days(p)}
                        for p in j["phases"]
                    ],
                }
                for j in u["jobs_data"]
            ],
            "people": [
                {"user": make_ref(r["user"], request), **days(r)}
                for r in u["users_data"]
            ],
            "roles": [{"role": r["role_name"], **days(r)} for r in u["roles_data"]],
            "services": [
                {"service": make_ref(r["service"], request), **days(r)}
                for r in u["services_data"]
            ],
            "monthly": [
                {
                    "month": m["month"],
                    "days": float(m["days"]),
                    "cumulative": float(m["cumulative"]),
                }
                for m in u["monthly_data"]
            ],
        }
