"""Skills, qualifications and services."""

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


from ....models import (
    AwardingBody,
    Qualification,
    Service,
    Skill,
    SkillCategory,
)


from ....selectors.catalogue import qualification_record_stats, skill_rating_counts
from ..fields import RefField, RefListField, RefSerializer, WebUrlField


class SkillCategorySerializer(serializers.ModelSerializer):
    web_url = WebUrlField()

    class Meta:
        model = SkillCategory
        fields = ["id", "name", "description", "slug", "web_url"]


class SkillSerializer(serializers.ModelSerializer):
    category = RefField()
    prerequisites = RefListField()
    related_skills = RefListField()
    web_url = WebUrlField()

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "description",
            "category",
            "slug",
            "prerequisites",
            "related_skills",
            "web_url",
        ]


class QualificationSerializer(serializers.ModelSerializer):
    awarding_body = RefField()
    tags = RefListField()
    web_url = WebUrlField()
    validity_period_display = serializers.CharField(read_only=True)

    class Meta:
        model = Qualification
        fields = [
            "id",
            "name",
            "short_name",
            "slug",
            "awarding_body",
            "tags",
            "description",
            "validity_period",
            "validity_period_display",
            "verification_required",
            "url",
            "guidance_url",
            "web_url",
        ]


class ServiceSerializer(serializers.ModelSerializer):
    skillsRequired = RefListField()
    skillsDesired = RefListField()
    qualificationsRequired = RefListField()
    qualificationsDesired = RefListField()
    web_url = WebUrlField()

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
            "web_url",
        ]


class SkillDetailSerializer(SkillSerializer):
    qualifications = RefListField()
    services_required = RefListField(source="services_skill_required")
    services_desired = RefListField(source="services_skill_desired")
    rating_counts = serializers.SerializerMethodField()

    class Meta(SkillSerializer.Meta):
        fields = SkillSerializer.Meta.fields + [
            "qualifications",
            "services_required",
            "services_desired",
            "rating_counts",
        ]

    @extend_schema_field(serializers.DictField(child=serializers.IntegerField()))
    def get_rating_counts(self, skill):
        """Active people per rating (``rating`` value → count)."""
        return {str(k): v for k, v in skill_rating_counts(skill).items()}


class ServiceListSerializer(ServiceSerializer):
    specialist_count = serializers.IntegerField(read_only=True)
    skilled_people_count = serializers.IntegerField(read_only=True)
    active_phases_count = serializers.IntegerField(read_only=True)
    risk_score = serializers.IntegerField(
        read_only=True, help_text="0 critical, 1 high, 2 medium, 3 low."
    )

    class Meta(ServiceSerializer.Meta):
        fields = ServiceSerializer.Meta.fields + [
            "specialist_count",
            "skilled_people_count",
            "active_phases_count",
            "risk_score",
        ]


class AwardingBodySerializer(serializers.ModelSerializer):
    class Meta:
        model = AwardingBody
        fields = ["id", "name", "slug", "url"]


class QualificationDetailSerializer(QualificationSerializer):
    demonstrated_skills = RefListField()
    services_required = RefListField(source="services_qual_required")
    services_desired = RefListField(source="services_qual_desired")
    record_counts = serializers.SerializerMethodField()

    class Meta(QualificationSerializer.Meta):
        fields = QualificationSerializer.Meta.fields + [
            "demonstrated_skills",
            "services_required",
            "services_desired",
            "record_counts",
        ]

    @extend_schema_field(serializers.DictField(child=serializers.IntegerField()))
    def get_record_counts(self, qualification):
        """``awarded``, ``in_progress``, ``lapsed``, ``expiring_soon`` (90 days)."""
        return qualification_record_stats(qualification, timezone.now().date())


class MatrixCategorySerializer(serializers.Serializer):
    category = RefSerializer()
    skills = RefSerializer(many=True)


class MatrixCellSerializer(serializers.Serializer):
    rating = serializers.IntegerField()
    interested = serializers.BooleanField()


class MatrixRowSerializer(serializers.Serializer):
    user = RefSerializer()
    ratings = serializers.DictField(
        child=MatrixCellSerializer(), help_text="Keyed by skill id."
    )


class ChoiceSerializer(serializers.Serializer):
    value = serializers.IntegerField()
    label = serializers.CharField()


class MatrixFiltersSerializer(serializers.Serializer):
    all_units = serializers.ListField(child=serializers.DictField())
    all_teams = serializers.ListField(child=serializers.DictField())
    all_categories = serializers.ListField(child=serializers.DictField())
    all_org_roles = serializers.ListField(child=serializers.DictField())


class SkillMatrixSerializer(serializers.Serializer):
    categories = MatrixCategorySerializer(many=True)
    rows = MatrixRowSerializer(many=True)
    rating_choices = ChoiceSerializer(many=True)
    filters = MatrixFiltersSerializer()


class CoverageCountsSerializer(serializers.Serializer):
    specialists = serializers.IntegerField()
    independent_only = serializers.IntegerField()
    support_only = serializers.IntegerField()
    missing_skills = serializers.IntegerField()
    total_capable = serializers.IntegerField()
    required_quals_holders = serializers.IntegerField()


class CoveragePeopleSerializer(serializers.Serializer):
    specialists = RefSerializer(many=True)
    independent_only = RefSerializer(many=True)
    support_only = RefSerializer(many=True)
    missing_skills = RefSerializer(many=True)
    required_quals_holders = RefSerializer(many=True)


class CoverageSkillSerializer(serializers.Serializer):
    skill = RefSerializer()
    total_users = serializers.IntegerField()
    specialists = serializers.IntegerField()
    independent = serializers.IntegerField()
    support_needed = serializers.IntegerField()
    coverage_percentage = serializers.FloatField()
    training_candidates = serializers.IntegerField()
    skill_gap = serializers.IntegerField(required=False)
    critical = serializers.BooleanField(required=False)
    opportunity_score = serializers.FloatField(required=False)


class CoverageSummarySerializer(serializers.Serializer):
    total_skilled_users = serializers.IntegerField()
    required_skills_count = serializers.IntegerField()
    desired_skills_count = serializers.IntegerField()
    critical_skills_count = serializers.IntegerField()
    avg_required_coverage = serializers.FloatField()
    avg_desired_coverage = serializers.FloatField()
    coverage_health = serializers.CharField()


class ServiceCoverageSerializer(serializers.Serializer):
    counts = CoverageCountsSerializer()
    people = CoveragePeopleSerializer(allow_null=True)
    required_skills = CoverageSkillSerializer(many=True)
    desired_skills = CoverageSkillSerializer(many=True)
    summary = CoverageSummarySerializer()
