"""Skills, qualifications and services."""

from rest_framework import serializers


from ....models import (
    Qualification,
    Service,
    Skill,
    SkillCategory,
)


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
