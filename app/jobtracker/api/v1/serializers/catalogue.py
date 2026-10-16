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
from ..fields import RefField, RefListField, WebUrlField


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
