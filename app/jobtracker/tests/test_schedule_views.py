import json
from django.test import RequestFactory, override_settings

from jobtracker import schedule_history
from jobtracker.models import TimeSlot
from jobtracker.views import scheduler as sched_views
from .test_schedule_history import ScheduleHistoryBase


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class HistoryViewTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()

    def _get(self, view, path, params, user):
        req = self.rf.get(path, params)
        req.user = user
        return view(req)

    def _post(self, view, path, data, user):
        req = self.rf.post(path, data)
        req.user = user
        return view(req)

    def test_history_lists_scope_with_can_revert(self):
        slot = self._delivery_slot()
        schedule_history.record_creates(self.actor, [slot])
        resp = self._get(
            sched_views.schedule_action_history,
            "/scheduler/history", {"job": self.job.pk}, self.actor,
        )
        data = json.loads(resp.content)
        self.assertEqual(len(data["actions"]), 1)
        self.assertTrue(data["actions"][0]["can_revert"])

    def test_history_hides_revert_for_other_user(self):
        slot = self._delivery_slot()
        schedule_history.record_creates(self.actor, [slot])
        resp = self._get(
            sched_views.schedule_action_history,
            "/scheduler/history", {"job": self.job.pk}, self.other,
        )
        data = json.loads(resp.content)
        self.assertFalse(data["actions"][0]["can_revert"])

    def test_revert_endpoint(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        resp = self._post(
            sched_views.schedule_action_revert,
            "/scheduler/action/revert", {"pk": action.pk}, self.actor,
        )
        data = json.loads(resp.content)
        self.assertTrue(data["ok"])
        self.assertFalse(TimeSlot.objects.filter(pk=slot.pk).exists())

    def test_revert_endpoint_forbidden_for_other(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        resp = self._post(
            sched_views.schedule_action_revert,
            "/scheduler/action/revert", {"pk": action.pk}, self.other,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(TimeSlot.objects.filter(pk=slot.pk).exists())

    def test_undo_endpoint_reverts_own_latest(self):
        first = self._internal_slot()
        schedule_history.record_creates(self.actor, [first])
        second = self._internal_slot()
        schedule_history.record_creates(self.actor, [second])
        resp = self._post(
            sched_views.schedule_action_undo, "/scheduler/action/undo", {}, self.actor
        )
        data = json.loads(resp.content)
        self.assertTrue(data["ok"])
        # Latest (second) undone; first remains.
        self.assertFalse(TimeSlot.objects.filter(pk=second.pk).exists())
        self.assertTrue(TimeSlot.objects.filter(pk=first.pk).exists())

    def test_undo_endpoint_nothing_to_undo(self):
        resp = self._post(
            sched_views.schedule_action_undo, "/scheduler/action/undo", {}, self.actor
        )
        data = json.loads(resp.content)
        self.assertFalse(data["ok"])

    def test_since_endpoint_returns_deltas(self):
        slot = self._delivery_slot()
        schedule_history.record_creates(self.actor, [slot])
        resp = self._get(
            sched_views.view_scheduler_slots_since,
            "/scheduler/timeslots/since", {"job": self.job.pk}, self.actor,
        )
        data = json.loads(resp.content)
        self.assertEqual(len(data["deltas"]), 1)
        self.assertEqual(data["deltas"][0]["upserts"][0]["id"], slot.pk)
        self.assertIn("now", data)
