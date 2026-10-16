"""Skills, qualifications and services."""

from rest_framework import serializers


from ....models import (
    Qualification,
    Service,
    Skill,
    SkillCategory,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


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
