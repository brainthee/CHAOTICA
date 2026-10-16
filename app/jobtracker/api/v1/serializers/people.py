"""Users, org units, leave and competency records."""

from decimal import Decimal

from cities_light.models import City
from rest_framework import serializers

from chaotica_utils.models import User, JobLevel
from chaotica_utils.models.leave import LeaveRequest

from ....models import (
    OrganisationalUnit,
    QualificationRecord,
    UserSkill,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    """Minimal user representation. PII (phone number, etc.) is deliberately
    excluded — programmatic clients get identity, not the full profile.

    ``job_title`` (free-text) and the current job level (from the
    ``UserJobLevel`` history, ``is_current=True``) are included: they are
    org-chart facts already shown across the UI, and drive HR/AAD-style
    automation. ``job_level`` is the short label (e.g. ``"JL5"``);
    ``job_level_label`` is the long description (may be null)."""

    job_level = serializers.SerializerMethodField()
    job_level_label = serializers.SerializerMethodField()
    city_name = serializers.CharField(source="city.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "job_title",
            "job_level",
            "job_level_label",
            "city",
            "city_name",
            "country",
        ]

    def get_job_level(self, obj):
        current = obj.get_current_level()
        return current.job_level.short_label if current else None

    def get_job_level_label(self, obj):
        current = obj.get_current_level()
        return current.job_level.long_label if current else None


class UserStatusUpdateSerializer(serializers.Serializer):
    """Write body for the ``users/{id}/set-status/`` action.

    Deliberately tiny: a single boolean so the endpoint can never be repurposed
    to edit arbitrary user fields."""

    is_active = serializers.BooleanField()


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Write body for ``users/{id}/update-profile/``.

    Partial update of org-chart profile facts only — the fields an HR / AAD sync
    legitimately owns. Sensitive/security fields (is_active, password, perms,
    email) are intentionally NOT writable here; account status has its own
    ``set-status`` action, and cost rates have ``set-cost``."""

    # City is a cities_light FK; accept it by primary key (nullable to clear).
    city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "job_title", "city", "country"]
        extra_kwargs = {
            "first_name": {"required": False},
            "last_name": {"required": False},
            "job_title": {"required": False},
            "country": {"required": False},
        }


class UserJobLevelUpdateSerializer(serializers.Serializer):
    """Write body for ``users/{id}/set-job-level/``.

    Either sets the current career level (by its short label, e.g. ``"JL5"``) or
    clears it. Resolving happens here so the view stays thin."""

    job_level = serializers.CharField(required=False, allow_blank=True)
    clear = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    # When the change actually took effect (defaults to today). A new assignment
    # is created with this date and the prior one is closed off (is_current=False).
    effective_from = serializers.DateField(required=False)

    def validate_effective_from(self, value):
        # Mirror UserJobLevel.clean(): an assignment can't start in the future.
        from django.utils import timezone

        if value and value > timezone.now().date():
            raise serializers.ValidationError(
                "Effective date cannot be in the future."
            )
        return value

    def validate(self, attrs):
        clear = attrs.get("clear", False)
        label = (attrs.get("job_level") or "").strip()
        if clear and label:
            raise serializers.ValidationError(
                "Provide either 'job_level' or 'clear', not both."
            )
        if not clear and not label:
            raise serializers.ValidationError(
                "Provide 'job_level' (short label) or set 'clear' to true."
            )
        if label:
            try:
                attrs["job_level_obj"] = JobLevel.objects.get(short_label=label)
            except JobLevel.DoesNotExist:
                raise serializers.ValidationError(
                    {"job_level": f"No job level with short label '{label}'."}
                )
        return attrs


class UserCostUpdateSerializer(serializers.Serializer):
    """Write body for ``users/{id}/set-cost/`` — a date-effective loaded cost rate.

    Mirrors the Operations → Loaded Cost Rates "set rate" action: add-only history, one
    row per effective date (re-posting the same date updates it)."""

    cost_per_hour = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )
    effective_from = serializers.DateField(required=False)


class OrganisationalUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganisationalUnit
        fields = ["id", "name", "slug"]


class OrganisationalUnitMemberSerializer(serializers.Serializer):
    """Slim representation of a user's membership in an org unit.

    Returned by ``GET /api/v1/org-units/{id}/members/``.  Sensitive fields
    (phone, cost rates, etc.) are deliberately excluded — this endpoint is
    about team composition, not HR records.

    ``is_lead`` is an annotation added by the viewset (a boolean derived from
    whether the member appears in the unit's ``leads`` M2M)."""

    user_id = serializers.IntegerField(source="member.id")
    first_name = serializers.CharField(source="member.first_name")
    last_name = serializers.CharField(source="member.last_name")
    email = serializers.EmailField(source="member.email")
    is_active = serializers.BooleanField(source="member.is_active")
    job_title = serializers.CharField(source="member.job_title", default=None)
    is_lead = serializers.BooleanField()  # annotated by viewset
    roles = serializers.SerializerMethodField()

    def get_roles(self, obj):
        return [r.name for r in obj.roles.all()]


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
