"""Clean, read-only serializers for the /api/v1/ API.

These are intentionally decoupled from the legacy ``jobtracker/serializers.py``
(which emits rendered HTML and DataTables row metadata for the UI). Everything
here is plain JSON: FKs as primary keys plus a compact ``*_name``/``*_display``
label, choice fields as ``*_display``, and no HTML.

Sensitive fields are deliberately omitted — see the module-level notes on each
serializer and the permission section of the implementation plan.
"""

from rest_framework import serializers

from chaotica_utils.models import User
from chaotica_utils.models.leave import LeaveRequest

from ...models import (
    Client,
    Job,
    OrganisationalUnit,
    Phase,
    Project,
    Qualification,
    QualificationRecord,
    Service,
    Skill,
    SkillCategory,
    TimeSlot,
    TimeSlotType,
    UserSkill,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    """Minimal user representation. PII (phone number, etc.) is deliberately
    excluded — programmatic clients get identity, not the full profile."""

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "is_active"]


class OrganisationalUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganisationalUnit
        fields = ["id", "name", "slug"]


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


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------


class PhaseSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    service_name = serializers.CharField(source="service.name", read_only=True)
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
            "service",
            "service_name",
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


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


class TimeSlotTypeSerializer(serializers.ModelSerializer):
    availability_display = serializers.CharField(
        source="get_availability_display", read_only=True
    )

    class Meta:
        model = TimeSlotType
        fields = [
            "id",
            "name",
            "built_in",
            "is_delivery",
            "is_working",
            "is_assignable",
            "availability",
            "availability_display",
        ]


class TimeSlotSerializer(serializers.ModelSerializer):
    slot_type_name = serializers.CharField(source="slot_type.name", read_only=True)
    deliveryRole_display = serializers.CharField(
        source="get_deliveryRole_display", read_only=True
    )
    is_confirmed = serializers.BooleanField(read_only=True)

    class Meta:
        model = TimeSlot
        # get_business_hours() / cost() are deliberately omitted — expensive and
        # not needed for a list feed.
        fields = [
            "id",
            "start",
            "end",
            "user",
            "slot_type",
            "slot_type_name",
            "phase",
            "project",
            "deliveryRole",
            "deliveryRole_display",
            "is_onsite",
            "is_confirmed",
            "updated",
        ]


# ---------------------------------------------------------------------------
# People / competency
# ---------------------------------------------------------------------------


class LeaveRequestSerializer(serializers.ModelSerializer):
    type_of_leave_display = serializers.CharField(
        source="get_type_of_leave_display", read_only=True
    )

    class Meta:
        model = LeaveRequest
        # affected_days() is omitted from the list serializer: it runs a
        # businessDuration calculation with per-row DB lookups.
        fields = [
            "id",
            "user",
            "requested_on",
            "start_date",
            "end_date",
            "type_of_leave",
            "type_of_leave_display",
            "notes",
            "authorised",
            "authorised_on",
            "authorised_by",
            "cancelled",
            "declined",
            "timeslot",
        ]


class SkillCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillCategory
        fields = ["id", "name", "description", "slug"]


class SkillSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    prerequisites = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    related_skills = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "description",
            "category",
            "category_name",
            "slug",
            "prerequisites",
            "related_skills",
        ]


class UserSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    rating_display = serializers.CharField(
        source="get_rating_display", read_only=True
    )

    class Meta:
        model = UserSkill
        fields = [
            "id",
            "user",
            "skill",
            "skill_name",
            "rating",
            "rating_display",
            "interested_in_improving_skill",
            "last_updated_on",
        ]


class QualificationSerializer(serializers.ModelSerializer):
    awarding_body_name = serializers.CharField(
        source="awarding_body.name", read_only=True
    )
    tags = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    validity_period_display = serializers.CharField(read_only=True)

    class Meta:
        model = Qualification
        fields = [
            "id",
            "name",
            "short_name",
            "slug",
            "awarding_body",
            "awarding_body_name",
            "tags",
            "description",
            "validity_period",
            "validity_period_display",
            "verification_required",
            "url",
            "guidance_url",
        ]


class QualificationRecordSerializer(serializers.ModelSerializer):
    qualification_name = serializers.CharField(
        source="qualification.name", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    is_lapsed = serializers.BooleanField(read_only=True)
    days_to_lapse = serializers.IntegerField(read_only=True)
    expiry_urgency = serializers.CharField(read_only=True)

    class Meta:
        model = QualificationRecord
        # certificate_file is deliberately excluded — it is served straight from
        # MEDIA with no access gate anywhere in the app.
        fields = [
            "id",
            "qualification",
            "qualification_name",
            "user",
            "status",
            "status_display",
            "attempt_date",
            "awarded_date",
            "lapse_date",
            "certificate_number",
            "notes",
            "verified_by",
            "verified_on",
            "is_lapsed",
            "days_to_lapse",
            "expiry_urgency",
        ]


class ServiceSerializer(serializers.ModelSerializer):
    skillsRequired = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    skillsDesired = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    qualificationsRequired = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )
    qualificationsDesired = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "link",
            "is_core",
            "skillsRequired",
            "skillsDesired",
            "qualificationsRequired",
            "qualificationsDesired",
        ]
