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


def _colours(context):
    """Scheduler colours, read once per serialisation (cached in context)."""
    if "schedule_colours" not in context:
        from ....utils import schedule_colours

        context["schedule_colours"] = schedule_colours()
    return context["schedule_colours"]


class SlotDisplaySerializer(serializers.Serializer):
    """How the main scheduler draws a slot (same rules as its own feed)."""

    title = serializers.CharField()
    colour = serializers.CharField()
    text_colour = serializers.CharField()
    tentative = serializers.BooleanField()
    can_edit = serializers.BooleanField()
    locked_reason = serializers.CharField(allow_null=True)
    rm_managed = serializers.BooleanField()
    edit_url = serializers.CharField(allow_null=True, help_text="Main-UI edit modal.")
    view_url = serializers.CharField(allow_null=True, help_text="Main-UI page.")
    icon = serializers.CharField(allow_null=True)


def slot_display(obj, context):
    data = obj.get_schedule_json(schedule_colours=_colours(context))
    return {
        "title": data.get("title") or "",
        "colour": data.get("backgroundColor") or data.get("color"),
        "text_colour": data.get("textColor"),
        "tentative": bool(data.get("is_tentative")),
        "can_edit": bool(data.get("can_edit")),
        "locked_reason": data.get("locked_reason"),
        "rm_managed": bool(data.get("rm_managed")),
        "edit_url": data.get("edit_url"),
        "view_url": data.get("viewURL"),
        "icon": data.get("icon"),
    }


class ScheduleTimeSlotSerializer(serializers.ModelSerializer):
    """Compact slot for the ``/schedule/`` composites: relations are ids (a
    window holds thousands of slots; labels come from the payload's lookups)."""

    slot_type_name = serializers.CharField(source="slot_type.name", read_only=True)
    deliveryRole_display = serializers.CharField(
        source="get_deliveryRole_display", read_only=True
    )
    is_confirmed = serializers.BooleanField(read_only=True)
    display = serializers.SerializerMethodField()
    # Set on /schedule/ windows (see build_schedule_payload).
    out_of_scope = serializers.BooleanField(read_only=True, required=False)

    @extend_schema_field(SlotDisplaySerializer)
    def get_display(self, slot):
        return slot_display(slot, self.context)

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
            "display",
            "out_of_scope",
        ]


class TimeSlotSerializer(ScheduleTimeSlotSerializer):
    # /timeslots/ is the plain record; drawing hints are for /schedule/.
    display = None
    user = RefField()
    slot_type = RefField()
    phase = RefField()
    project = RefField()

    class Meta(ScheduleTimeSlotSerializer.Meta):
        fields = [
            f
            for f in ScheduleTimeSlotSerializer.Meta.fields
            if f not in ("display", "out_of_scope")
        ]


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
    country = serializers.CharField(allow_null=True, help_text="For matching holidays.")
    availability = serializers.FloatField()
    utilisation = serializers.FloatField()
    business_hours = serializers.DictField()


class TimeSlotCommentSerializer(serializers.ModelSerializer):
    """A scheduler comment (``user`` as an id in schedule composites)."""

    display = serializers.SerializerMethodField()

    class Meta:
        model = TimeSlotComment
        fields = ["id", "start", "end", "user", "comment", "display"]

    @extend_schema_field(SlotDisplaySerializer)
    def get_display(self, comment):
        return slot_display(comment, self.context)


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
    business_hours = serializers.DictField(help_text="startTime, endTime, daysOfWeek.")


class ScheduleBoundsSerializer(serializers.Serializer):
    start = serializers.DateTimeField(allow_null=True)
    end = serializers.DateTimeField(allow_null=True)


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
