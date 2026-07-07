"""Regression tests for the permission hardening (see fix/security-permission-hardening).

These verify that the scheduler's read/mutation endpoints and the version-control
(undo/revert) layer enforce object-level scheduling / view permissions, closing
the side-steps found in the security review. The base fixtures' ``actor`` is a
superuser (first user created), so these tests create dedicated NON-superuser
users with explicit guardian perms to actually exercise the gates.
"""
import json
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings
from guardian.shortcuts import assign_perm, remove_perm

from chaotica_utils.models import User
from jobtracker import schedule_history
from jobtracker.models import TimeSlot
from jobtracker.views import scheduler as sched_views
from .test_schedule_history import ScheduleHistoryBase


def _reload(user):
    """Return a fresh User instance so guardian's per-request perm cache resets."""
    return User.objects.get(pk=user.pk)


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class SchedulerPermissionTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        # A scheduler: may view + schedule the unit.
        self.scheduler = User.objects.create_user(
            email="sched@test.com", password="pw12345"
        )
        assign_perm("jobtracker.can_schedule_job", self.scheduler, self.unit)
        assign_perm("jobtracker.view_job_schedule", self.scheduler, self.unit)
        self.scheduler = _reload(self.scheduler)
        # An outsider: no perms on this unit at all.
        self.outsider = User.objects.create_user(
            email="outsider@test.com", password="pw12345"
        )

    def _get(self, view, path, params, user):
        req = self.rf.get(path, params)
        req.user = user
        return view(req)

    def _post(self, view, path, data, user):
        req = self.rf.post(path, data)
        req.user = user
        return view(req)

    # ---- F4: history / delta endpoints must not leak a job you can't view ----

    def test_history_denied_scope_returns_empty(self):
        schedule_history.record_creates(self.actor, [self._delivery_slot()])
        resp = self._get(
            sched_views.schedule_action_history,
            "/scheduler/history", {"job": self.job.pk}, self.outsider,
        )
        self.assertEqual(json.loads(resp.content)["actions"], [])

    def test_since_denied_scope_returns_no_deltas(self):
        schedule_history.record_creates(self.actor, [self._delivery_slot()])
        resp = self._get(
            sched_views.view_scheduler_slots_since,
            "/scheduler/timeslots/since", {"job": self.job.pk}, self.outsider,
        )
        self.assertEqual(json.loads(resp.content)["deltas"], [])

    def test_since_allowed_scope_returns_deltas(self):
        slot = self._delivery_slot()
        schedule_history.record_creates(self.actor, [slot])
        resp = self._get(
            sched_views.view_scheduler_slots_since,
            "/scheduler/timeslots/since", {"job": self.job.pk}, self.scheduler,
        )
        deltas = json.loads(resp.content)["deltas"]
        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0]["upserts"][0]["id"], slot.pk)

    def test_global_deltas_filtered_to_viewable_users(self):
        # A comment slot for the (unrelated) actor. The outsider shares no unit
        # with the actor, so a global-scope delta must not expose that slot.
        from jobtracker.models import TimeSlotComment
        comment = TimeSlotComment.objects.create(
            user=self.actor, comment="x", start=self.start, end=self.end
        )
        schedule_history.record_creates(self.actor, [comment])
        resp = self._get(
            sched_views.view_scheduler_slots_since,
            "/scheduler/timeslots/since", {}, self.outsider,
        )
        deltas = json.loads(resp.content)["deltas"]
        # The action is global-scoped; its only upsert is for a user the outsider
        # can't see, so upserts must be filtered out.
        for delta in deltas:
            self.assertEqual(delta["upserts"], [])

    # ---- F6: undo/revert must re-check scheduling perm on the target ----

    def test_revert_allowed_for_scheduler_actor(self):
        action = schedule_history.record_creates(
            self.scheduler, [self._delivery_slot()]
        )
        self.assertTrue(action.can_revert(self.scheduler))

    def test_revert_denied_after_losing_schedule_perm(self):
        action = schedule_history.record_creates(
            self.scheduler, [self._delivery_slot()]
        )
        remove_perm("jobtracker.can_schedule_job", self.scheduler, self.unit)
        lost = _reload(self.scheduler)
        self.assertFalse(action.can_revert(lost))
        with self.assertRaises(PermissionDenied):
            schedule_history.revert(action, lost)

    # ---- F1: slot delete views must enforce object-level scheduling perm ----

    def test_delete_slot_denied_for_outsider(self):
        slot = self._delivery_slot()
        view = sched_views.JobSlotDeleteView.as_view()
        req = self.rf.post("/scheduler/timeslot/delete/{}".format(slot.pk))
        req.user = self.outsider
        with self.assertRaises(PermissionDenied):
            view(req, pk=slot.pk)
        self.assertTrue(TimeSlot.objects.filter(pk=slot.pk).exists())

    def test_delete_slot_allowed_for_scheduler(self):
        slot = self._delivery_slot()
        view = sched_views.JobSlotDeleteView.as_view()
        req = self.rf.post(
            "/scheduler/timeslot/delete/{}".format(slot.pk),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        req.user = self.scheduler
        resp = view(req, pk=slot.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(TimeSlot.objects.filter(pk=slot.pk).exists())


class DeltaFilterUnitTests(ScheduleHistoryBase):
    def test_filter_delta_for_users_none_is_passthrough(self):
        delta = {"upserts": [{"userId": 1}, {"userId": 2}], "removals": []}
        self.assertEqual(schedule_history.filter_delta_for_users(delta, None), delta)

    def test_filter_delta_for_users_restricts_upserts(self):
        delta = {"upserts": [{"userId": 1}, {"userId": 2}], "removals": [{"id": 9}]}
        out = schedule_history.filter_delta_for_users(delta, {2})
        self.assertEqual(out["upserts"], [{"userId": 2}])
        self.assertEqual(out["removals"], [{"id": 9}])
