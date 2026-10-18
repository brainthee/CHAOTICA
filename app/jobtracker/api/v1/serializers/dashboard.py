"""Dashboard, alarms, stats and notifications."""

from rest_framework import serializers

from ..fields import RefField


class QueueSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    resource = serializers.ChoiceField(choices=["jobs", "phases"])


class ConsultantStatsSerializer(serializers.Serializer):
    jobs_participated = serializers.IntegerField()
    jobs_led = serializers.IntegerField()
    reports_authored = serializers.IntegerField()
    scoped = serializers.IntegerField()
    qaed = serializers.IntegerField()


class MonthlySeriesSerializer(serializers.Serializer):
    """13 months, oldest first: ``months`` are first-of-month dates; 0 = no rating."""

    months = serializers.ListField(child=serializers.CharField())
    data = serializers.ListField(child=serializers.FloatField())


class UserStatsSerializer(serializers.Serializer):
    consultant = ConsultantStatsSerializer()
    avg_tqa_rating = serializers.FloatField(allow_null=True)
    avg_pqa_rating = serializers.FloatField(allow_null=True)
    tqa_feedback_12mo = MonthlySeriesSerializer()
    pqa_feedback_12mo = MonthlySeriesSerializer()


class DashboardStatsSerializer(UserStatsSerializer):
    utilisation_30d = serializers.FloatField(allow_null=True)
    utilisation_prior_30d = serializers.FloatField(allow_null=True)
    utilisation_target = serializers.FloatField(allow_null=True)
    leave_remaining_days = serializers.FloatField(allow_null=True)
    leave_pending_requests = serializers.IntegerField()


class TeamUtilisationSerializer(serializers.Serializer):
    user = RefField()
    utilisation = serializers.FloatField(allow_null=True)


class DashboardSerializer(serializers.Serializer):
    queues = QueueSerializer(many=True)
    alarm_counts = serializers.DictField(child=serializers.IntegerField())
    stats = DashboardStatsSerializer()
    team_unit = RefField(allow_null=True)
    team = TeamUtilisationSerializer(many=True)
    capabilities = serializers.DictField(child=serializers.BooleanField())


class AlarmItemSerializer(serializers.Serializer):
    ref = RefField(source="obj")
    date = serializers.DateField(allow_null=True)
    people = serializers.SerializerMethodField()
    message = serializers.CharField()

    def get_people(self, item) -> list[dict]:
        field = RefField()
        field.bind("people", self)
        return [field.to_representation(p) for p in item["people"]]


class AlarmGroupSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    severity = serializers.ChoiceField(choices=["critical", "warning"])
    items = AlarmItemSerializer(many=True)


class AlarmsSerializer(serializers.Serializer):
    overdue = AlarmGroupSerializer(many=True)
    stale = AlarmGroupSerializer(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())


class NotificationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.IntegerField()
    type_display = serializers.CharField()
    timestamp = serializers.DateTimeField()
    timestamp_human = serializers.CharField(help_text="e.g. '3 hours ago'.")
    title = serializers.CharField()
    message = serializers.CharField()
    link = serializers.CharField(allow_null=True)
    read = serializers.BooleanField()
    entity_type = serializers.CharField(allow_null=True)
    entity_id = serializers.IntegerField(allow_null=True)


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False, max_length=500
    )
    read = serializers.BooleanField(default=True)


class UpdatedCountSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
    unread_count = serializers.IntegerField()
