from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.test import override_settings

from jobtracker import schedule_history
from jobtracker.models import TimeSlot
from .test_schedule_history import ScheduleHistoryBase


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class BuildDeltaTests(ScheduleHistoryBase):
    def test_build_delta_create(self):
        slot = self._delivery_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        delta = schedule_history.build_delta(action)
        self.assertEqual(len(delta["upserts"]), 1)
        self.assertEqual(delta["removals"], [])
        self.assertEqual(delta["upserts"][0]["id"], slot.pk)
        # datetimes must be JSON/msgpack-safe (ISO strings, not datetime objects).
        self.assertIsInstance(delta["upserts"][0]["start"], str)

    def test_build_delta_delete(self):
        slot = self._internal_slot()
        before = schedule_history.snapshot(slot)
        pk = slot.pk
        slot.delete()
        action = schedule_history.record_deletes(self.actor, [before])
        delta = schedule_history.build_delta(action)
        self.assertEqual(delta["upserts"], [])
        self.assertEqual(delta["removals"], [{"is_comment": False, "id": pk}])


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class BroadcastTests(ScheduleHistoryBase):
    def test_record_broadcasts_to_scope_groups(self):
        layer = get_channel_layer()
        async_to_sync(layer.group_add)("schedule_global", "obs-global")
        async_to_sync(layer.group_add)(
            "schedule_job_{}".format(self.job.pk), "obs-job"
        )

        slot = self._delivery_slot()
        action = schedule_history.record_creates(self.actor, [slot])

        for channel in ("obs-global", "obs-job"):
            msg = async_to_sync(layer.receive)(channel)
            self.assertEqual(msg["type"], "schedule.delta")
            self.assertEqual(msg["delta"]["action_id"], action.pk)
            self.assertEqual(msg["delta"]["upserts"][0]["id"], slot.pk)

    def test_internal_change_only_hits_global(self):
        layer = get_channel_layer()
        async_to_sync(layer.group_add)("schedule_global", "obs-global2")
        slot = self._internal_slot()
        schedule_history.record_creates(self.actor, [slot])
        msg = async_to_sync(layer.receive)("obs-global2")
        self.assertEqual(msg["type"], "schedule.delta")
