"""Timeslots and composite schedule windows."""

from rest_framework import serializers

from .people import LeaveRequestSerializer

from chaotica_utils.models import Holiday

from ....models import (
    TimeSlot,
    TimeSlotType,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
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


class HolidaySerializer(serializers.ModelSerializer):
    """Public/non-working day. Applies to a country; a consumer matches it to a
    user via the user's country."""

    class Meta:
        model = Holiday
        fields = ["id", "date", "country", "reason"]


class ScheduleUserAvailabilitySerializer(serializers.Serializer):
    """Per-user availability/utilisation for a schedule window (documentation /
    schema shape — the values come from ``collect_schedule_members``)."""

    user = serializers.IntegerField()
    availability = serializers.FloatField()
    utilisation = serializers.FloatField()
    business_hours = serializers.DictField()


class ScheduleSerializer(serializers.Serializer):
    """Composite read-only schedule window: work timeslots, leave, holidays and
    per-user availability for ``[start, end]``. Assembled by
    ``jobtracker.api.v1.schedule.build_schedule_payload``."""

    start = serializers.DateField()
    end = serializers.DateField()
    users = ScheduleUserAvailabilitySerializer(many=True)
    timeslots = TimeSlotSerializer(many=True)
    leave = LeaveRequestSerializer(many=True)
    holidays = HolidaySerializer(many=True)
