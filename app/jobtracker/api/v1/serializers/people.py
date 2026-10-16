"""Users, org units, leave and competency records."""

from decimal import Decimal

from cities_light.models import City
from rest_framework import serializers

from drf_spectacular.utils import extend_schema_field

from ....selectors.orgunits import unit_member_rows
from ..fields import RefField, RefListField, WebUrlField

from chaotica_utils.models import User, JobLevel
from chaotica_utils.models.leave import LeaveRequest

from ....models import (
    OrganisationalUnit,
    QualificationRecord,
    UserSkill,
)


class UserSerializer(serializers.ModelSerializer):
    """Minimal user representation. PII (phone number, etc.) is deliberately
    excluded — programmatic clients get identity, not the full profile.

    ``job_title`` (free-text) and the current job level (from the
    ``UserJobLevel`` history, ``is_current=True``) are included: they are
    org-chart facts already shown across the UI, and drive HR/AAD-style
    automation. ``job_level`` is the short label (e.g. ``"JL5"``);
    ``job_level_label`` is the long description (may be null)."""

    display = serializers.CharField(source="__str__", read_only=True)
    job_level = serializers.SerializerMethodField()
    job_level_label = serializers.SerializerMethodField()
    city = RefField()
    web_url = WebUrlField()

    class Meta:
        model = User
        fields = [
            "id",
            "display",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "job_title",
            "job_level",
            "job_level_label",
            "city",
            "country",
            "web_url",
        ]

    def get_job_level(self, obj) -> str | None:
        current = obj.get_current_level()
        return current.job_level.short_label if current else None

    def get_job_level_label(self, obj) -> str | None:
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
            raise serializers.ValidationError("Effective date cannot be in the future.")
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
    web_url = WebUrlField()

    class Meta:
        model = OrganisationalUnit
        fields = ["id", "name", "slug", "web_url"]


class OrganisationalUnitMemberSerializer(serializers.Serializer):
    """Slim representation of a user's membership in an org unit.

    Returned by ``GET /api/v1/org-units/{id}/members/``.  Sensitive fields
    (phone, cost rates, etc.) are deliberately excluded — this endpoint is
    about team composition, not HR records.

    ``is_lead`` is an annotation added by the viewset (a boolean derived from
    whether the member appears in the unit's ``leads`` M2M)."""

    user = RefField(source="member")
    email = serializers.EmailField(source="member.email")
    is_active = serializers.BooleanField(source="member.is_active")
    job_title = serializers.CharField(source="member.job_title", default=None)
    is_lead = serializers.BooleanField()  # annotated by viewset
    roles = serializers.SerializerMethodField()

    def get_roles(self, obj) -> list[str]:
        return [r.name for r in obj.roles.all()]


class LeaveRequestSerializer(serializers.ModelSerializer):
    type_of_leave_display = serializers.CharField(
        source="get_type_of_leave_display", read_only=True
    )
    user = RefField()
    authorised_by = RefField()

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


class LeaveRequestListSerializer(LeaveRequestSerializer):
    """``/leave-requests/``: adds whether it clashes with booked delivery work
    and whether the caller may approve it."""

    overlaps_work = serializers.BooleanField(source="overlaps_work_ann", read_only=True)
    can_authorise = serializers.SerializerMethodField()

    class Meta(LeaveRequestSerializer.Meta):
        fields = LeaveRequestSerializer.Meta.fields + ["overlaps_work", "can_authorise"]

    def get_can_authorise(self, leave) -> bool:
        request = self.context.get("request")
        if request is None or leave.authorised or leave.declined or leave.cancelled:
            return False
        return bool(leave.can_user_auth(request.user))


class UserSkillSerializer(serializers.ModelSerializer):
    user = RefField()
    skill = RefField()
    rating_display = serializers.CharField(source="get_rating_display", read_only=True)

    class Meta:
        model = UserSkill
        fields = [
            "id",
            "user",
            "skill",
            "rating",
            "rating_display",
            "interested_in_improving_skill",
            "last_updated_on",
        ]


class QualificationRecordSerializer(serializers.ModelSerializer):
    qualification = RefField()
    user = RefField()
    verified_by = RefField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
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


class UserContactSerializer(serializers.Serializer):
    email = serializers.EmailField()
    notification_email = serializers.EmailField(allow_null=True)
    phone = serializers.CharField(source="phone_number", allow_blank=True)

    def to_representation(self, user):
        data = super().to_representation(user)
        data["phone"] = str(user.phone_number) if user.phone_number else ""
        return data


class UnitMembershipRefSerializer(serializers.Serializer):
    unit = RefField()
    roles = serializers.SerializerMethodField()

    def get_roles(self, membership) -> list[str]:
        return [r.name for r in membership.roles.all()]


class UserDetailSerializer(UserSerializer):
    """``/users/{id}/``: the profile card. ``contact`` (email addresses and
    phone) only for yourself and holders of ``view_user``."""

    avatar_url = serializers.SerializerMethodField()
    manager = RefField()
    acting_manager = RefField()
    contact = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            "alias",
            "avatar_url",
            "manager",
            "acting_manager",
            "contact",
        ]

    def get_avatar_url(self, user) -> str:
        request = self.context.get("request")
        url = user.get_avatar_url()
        return request.build_absolute_uri(url) if request else url

    @extend_schema_field(UserContactSerializer(allow_null=True))
    def get_contact(self, user):
        if not self.context["policy"].can("user.view", user):
            return None
        return UserContactSerializer(user).data


class TeamMembershipSerializer(serializers.Serializer):
    team = RefField()
    joined_at = serializers.DateField(allow_null=True)


class SkillRatingSerializer(serializers.Serializer):
    skill = RefField()
    category = serializers.CharField(source="skill.category.name")
    rating = serializers.IntegerField()
    rating_display = serializers.CharField(source="get_rating_display")
    interested_in_improving_skill = serializers.BooleanField()


class QualificationSummarySerializer(serializers.Serializer):
    qualification = RefField()
    status = serializers.IntegerField()
    status_display = serializers.CharField(source="get_status_display")
    awarded_date = serializers.DateField(allow_null=True)
    lapse_date = serializers.DateField(allow_null=True)


class UserProfileSerializer(UserDetailSerializer):
    """``/users/{id}/profile/``. ``skills`` / ``qualifications`` are null unless
    you may see this person's competency records (``/user-skills/`` rules)."""

    units = serializers.SerializerMethodField()
    teams = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    qualifications = serializers.SerializerMethodField()

    class Meta(UserDetailSerializer.Meta):
        fields = UserDetailSerializer.Meta.fields + [
            "units",
            "teams",
            "skills",
            "qualifications",
        ]

    @extend_schema_field(UnitMembershipRefSerializer(many=True))
    def get_units(self, user):
        memberships = (
            user.unit_memberships.filter(left_date__isnull=True)
            .select_related("unit")
            .prefetch_related("roles")
        )
        return UnitMembershipRefSerializer(
            memberships, many=True, context=self.context
        ).data

    @extend_schema_field(TeamMembershipSerializer(many=True))
    def get_teams(self, user):
        rows = user.teams.filter(left_at__isnull=True).select_related("team")
        return TeamMembershipSerializer(rows, many=True, context=self.context).data

    @extend_schema_field(SkillRatingSerializer(many=True, allow_null=True))
    def get_skills(self, user):
        if not self.context["policy"].can("user.view_skills", user):
            return None
        rows = user.skills.select_related("skill__category").order_by("skill__name")
        return SkillRatingSerializer(rows, many=True, context=self.context).data

    @extend_schema_field(QualificationSummarySerializer(many=True, allow_null=True))
    def get_qualifications(self, user):
        if not self.context["policy"].can("user.view_qualifications", user):
            return None
        rows = user.qualifications.select_related("qualification__awarding_body")
        return QualificationSummarySerializer(
            rows, many=True, context=self.context
        ).data


class UnitMemberRowSerializer(serializers.Serializer):
    user = RefField(source="member")
    roles = serializers.SerializerMethodField()
    is_consultant = serializers.BooleanField()
    is_deactivated = serializers.BooleanField()
    util_pct = serializers.FloatField()
    active_job_count = serializers.IntegerField()

    def get_roles(self, membership) -> list[str]:
        return [r.name for r in membership.roles.all()]


class OrganisationalUnitDetailSerializer(OrganisationalUnitSerializer):
    """``/org-units/{id}/``: the unit page's team table and header figures."""

    leads = RefListField()
    members = serializers.SerializerMethodField()
    utilisation_4wk = serializers.SerializerMethodField()

    class Meta(OrganisationalUnitSerializer.Meta):
        fields = OrganisationalUnitSerializer.Meta.fields + [
            "description",
            "leads",
            "members",
            "utilisation_4wk",
        ]

    def _rows(self, unit):
        if not hasattr(self, "_member_rows"):
            self._member_rows = unit_member_rows(unit)
        return self._member_rows

    @extend_schema_field(UnitMemberRowSerializer(many=True))
    def get_members(self, unit):
        rows, _pct = self._rows(unit)
        return UnitMemberRowSerializer(rows, many=True, context=self.context).data

    def get_utilisation_4wk(self, unit) -> float:
        return float(self._rows(unit)[1])
