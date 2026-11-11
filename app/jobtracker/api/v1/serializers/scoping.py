"""Scoping templates + the scope calculator."""

from rest_framework import serializers

from ....models.scoping import ScopingField, ScopingTemplate


class ScopingFieldSerializer(serializers.ModelSerializer):
    """One question within a template, including its options so a client can
    render the questionnaire and know how each field is used in the calc."""

    field_type_display = serializers.CharField(
        source="get_field_type_display", read_only=True
    )
    calc_role_display = serializers.CharField(
        source="get_calc_role_display", read_only=True
    )

    class Meta:
        model = ScopingField
        fields = [
            "id",
            "order",
            "label",
            "slug",
            "help_text",
            "field_type",
            "field_type_display",
            "required",
            "default",
            "options",
            "calc_role",
            "calc_role_display",
            "rate",
            "weight",
        ]


class ScopingTemplateSerializer(serializers.ModelSerializer):
    """A scoping template with its fields — the questionnaire definition."""

    fields = ScopingFieldSerializer(many=True, read_only=True)
    calc_mode_display = serializers.CharField(
        source="get_calc_mode_display", read_only=True
    )

    class Meta:
        model = ScopingTemplate
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "is_active",
            "calc_mode",
            "calc_mode_display",
            "sizing_combine",
            "fields",
        ]


class ScopingCalcInputSerializer(serializers.Serializer):
    """POST body for the scope calculator."""

    template = serializers.CharField(
        help_text="Template id or slug to evaluate against."
    )
    answers = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        default=dict,
        help_text="Map of field slug -> answer value.",
    )


class ScopingCalcResultSerializer(serializers.Serializer):
    """The engine result for a scored scope."""

    testing_days = serializers.FloatField()
    reporting_days = serializers.FloatField()
    delivery_hours = serializers.FloatField()
    reporting_hours = serializers.FloatField()
    justification = serializers.ListField(child=serializers.CharField())
    errors = serializers.ListField(child=serializers.CharField())
