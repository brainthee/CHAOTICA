"""Timeslots and composite schedule windows."""

from rest_framework import serializers

from chaotica_utils.models import Holiday

from drf_spectacular.utils import extend_schema_field

from ....models import (
    TimeSlot,
    TimeSlotComment,
    TimeSlotType,
)
from ..fields import RefField, RefSerializer
from .people import LeaveRequestSerializer


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


class ScheduleTimeSlotSerializer(serializers.ModelSerializer):
    """Compact slot for the ``/schedule/`` composites: relations are ids (a
    window holds thousands of slots; labels come from the payload's lookups)."""

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


class TimeSlotSerializer(ScheduleTimeSlotSerializer):
    user = RefField()
    slot_type = RefField()
    phase = RefField()
    project = RefField()


class ScheduleLeaveSerializer(LeaveRequestSerializer):
    """Compact leave for the ``/schedule/`` composites (relations as ids)."""

    user = serializers.PrimaryKeyRelatedField(read_only=True)
    authorised_by = serializers.PrimaryKeyRelatedField(read_only=True)


class HolidaySerializer(serializers.ModelSerializer):
    """Public/non-working day. Applies to a country; a consumer matches it to a
    user via the user's country."""

    country = serializers.SerializerMethodField()

    class Meta:
        model = Holiday
        fields = ["id", "date", "country", "reason"]

    def get_country(self, holiday) -> str | None:
        # A null CountryField still reads back as an (empty) Country object.
        return holiday.country.code if holiday.country else None


class ScheduleUserAvailabilitySerializer(serializers.Serializer):
    """Per-user availability/utilisation for a schedule window (documentation /
    schema shape — the values come from ``collect_schedule_members``)."""

    user = serializers.IntegerField()
    availability = serializers.FloatField()
    utilisation = serializers.FloatField()
    business_hours = serializers.DictField()


class TimeSlotCommentSerializer(serializers.ModelSerializer):
    """A scheduler comment (``user`` as an id in schedule composites)."""

    class Meta:
        model = TimeSlotComment
        fields = ["id", "start", "end", "user", "comment"]


class AvailabilityRunSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()


class UserAvailabilityRunsSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    runs = AvailabilityRunSerializer(many=True)


class ScheduleRefsSerializer(serializers.Serializer):
    """Labels for every phase / project a slot in the window points at,
    keyed by id (as a string)."""

    phases = serializers.DictField(child=RefSerializer())
    projects = serializers.DictField(child=RefSerializer())


class ScheduleScopeSerializer(serializers.Serializer):
    """Set on job/phase/project schedules: slots outside ``phase_ids`` /
    ``project_ids`` are the people's other commitments (show faded)."""

    phase_ids = serializers.ListField(child=serializers.IntegerField(), allow_null=True)
    project_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_null=True
    )
    hard = serializers.BooleanField()


class ScheduleSerializer(serializers.Serializer):
    """Composite read-only schedule window: work timeslots, leave, holidays and
    per-user availability for ``[start, end]``. Assembled by
    ``jobtracker.api.v1.schedule.build_schedule_payload``."""

    start = serializers.DateField()
    end = serializers.DateField()
    users = ScheduleUserAvailabilitySerializer(many=True)
    timeslots = ScheduleTimeSlotSerializer(many=True)
    leave = ScheduleLeaveSerializer(many=True)
    holidays = HolidaySerializer(many=True)
    comments = TimeSlotCommentSerializer(many=True)
    availability = UserAvailabilityRunsSerializer(many=True)
    refs = ScheduleRefsSerializer()
    scope = ScheduleScopeSerializer(allow_null=True)


class ScheduleResourceSerializer(RefSerializer):
    """A scheduler row: the user as a ref plus what the row header shows."""

    first_name = serializers.CharField()
    last_name = serializers.CharField()
    job_level_label = serializers.CharField()
    org_unit = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    availability = serializers.FloatField()
    utilisation = serializers.FloatField()


class ScheduleResourcesSerializer(serializers.Serializer):
    users = ScheduleResourceSerializer(many=True)


class ScheduleActionSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    created = serializers.DateTimeField()
    actor = RefField()
    action_type = serializers.CharField()
    summary = serializers.CharField()
    forced = serializers.BooleanField()
    override_reason = serializers.CharField(allow_blank=True)
    job = serializers.IntegerField(source="job_id", allow_null=True)
    phase = serializers.IntegerField(source="phase_id", allow_null=True)
    reverted = serializers.BooleanField()
    reverted_by = serializers.IntegerField(source="reverted_by_id", allow_null=True)
    is_revert = serializers.SerializerMethodField()
    can_revert = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    def get_is_revert(self, action) -> bool:
        from ....models.schedule_action import ScheduleActionType

        return action.action_type == ScheduleActionType.REVERT

    def get_can_revert(self, action) -> bool:
        return action.can_revert(self.context["request"].user)

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_items(self, action):
        """``[{model, id, change: added|changed|removed}]``"""
        from ....schedule_history import _describe_item

        return [
            {"model": item["model"], "id": item["pk"], "change": _describe_item(item)}
            for item in action.payload or []
        ]


class ScheduleDeltaSerializer(serializers.Serializer):
    action_id = serializers.IntegerField()
    created = serializers.DateTimeField()
    actor_id = serializers.IntegerField(allow_null=True)
    action_type = serializers.CharField()
    timeslots = ScheduleTimeSlotSerializer(many=True)
    comments = TimeSlotCommentSerializer(many=True)
    removed_timeslots = serializers.ListField(child=serializers.IntegerField())
    removed_comments = serializers.ListField(child=serializers.IntegerField())


class ScheduleDeltasSerializer(serializers.Serializer):
    deltas = ScheduleDeltaSerializer(many=True)
    now = serializers.DateTimeField()
