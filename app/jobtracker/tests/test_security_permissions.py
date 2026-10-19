"""Regression tests for the permission hardening (see fix/security-permission-hardening).

These verify that the scheduler's read/mutation endpoints and the version-control
(undo/revert) layer enforce object-level scheduling / view permissions, closing
the side-steps found in the security review. The base fixtures' ``actor`` is a
superuser (first user created), so these tests create dedicated NON-superuser
users with explicit guardian perms to actually exercise the gates.
"""
import json
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings
from django.utils import timezone
from guardian.shortcuts import assign_perm, remove_perm
from rest_framework.test import APIClient

from chaotica_utils.models import User
from jobtracker import schedule_history
from jobtracker.models import TimeSlot
from jobtracker.enums import PhaseStatuses, TimeSlotDeliveryRole
from jobtracker.views import scheduler as sched_views
from .test_schedule_history import ScheduleHistoryBase


def _reload(user):
    """Return a fresh User instance so guardian's per-request perm cache resets."""
    return User.objects.get(pk=user.pk)


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    ALLOWED_HOSTS=["testserver"],
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

    def _api(self, path, params, user):
        """History and deltas are read from /api/v1/ now."""
        client = APIClient(HTTP_HOST="testserver")
        client.force_authenticate(user)
        return client.get(path, params).json()

    def _since(self):
        return (timezone.now() - timedelta(minutes=5)).isoformat()

    def _post(self, view, path, data, user):
        req = self.rf.post(path, data)
        req.user = user
        return view(req)

    # ---- F4: history / delta endpoints must not leak a job you can't view ----

    def test_history_denied_scope_returns_empty(self):
        schedule_history.record_creates(self.actor, [self._delivery_slot()])
        actions = self._api(
            "/api/v1/schedule/actions/", {"job": self.job.pk}, self.outsider
        )
        self.assertEqual(actions, [])

    def test_since_denied_scope_returns_no_deltas(self):
        schedule_history.record_creates(self.actor, [self._delivery_slot()])
        data = self._api(
            "/api/v1/schedule/deltas/",
            {"job": self.job.pk, "since": self._since()},
            self.outsider,
        )
        self.assertEqual(data["deltas"], [])

    def test_since_allowed_scope_returns_deltas(self):
        slot = self._delivery_slot()
        schedule_history.record_creates(self.actor, [slot])
        deltas = self._api(
            "/api/v1/schedule/deltas/",
            {"job": self.job.pk, "since": self._since()},
            self.scheduler,
        )["deltas"]
        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0]["timeslots"][0]["id"], slot.pk)

    def test_global_deltas_filtered_to_viewable_users(self):
        # A comment slot for the (unrelated) actor. The outsider shares no unit
        # with the actor, so a global-scope delta must not expose that slot.
        from jobtracker.models import TimeSlotComment
        comment = TimeSlotComment.objects.create(
            user=self.actor, comment="x", start=self.start, end=self.end
        )
        schedule_history.record_creates(self.actor, [comment])
        deltas = self._api(
            "/api/v1/schedule/deltas/", {"since": self._since()}, self.outsider
        )["deltas"]
        # The action is global-scoped; its only upsert is for a user the outsider
        # can't see, so it must be filtered out.
        for delta in deltas:
            self.assertEqual(delta["comments"], [])
            self.assertEqual(delta["timeslots"], [])

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


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class SchedulerCrossUnitTests(ScheduleHistoryBase):
    """A scheduler of unit A must not book onto, or move slots into, unit B —
    whatever phase / user the request smuggles in."""

    def setUp(self):
        super().setUp()
        from jobtracker.models import OrganisationalUnit, OrganisationalUnitMember, Job, Phase

        self.rf = RequestFactory()
        self.unit_b = OrganisationalUnit.objects.create(name="Other Unit")
        self.job_b = Job.objects.create(
            unit=self.unit_b, client=self.client_obj, title="Other Job",
            created_by=self.actor, account_manager=self.actor,
        )
        # Schedulable, so these tests exercise the cross-unit permission check
        # rather than the (earlier) "Draft phases can't be booked" rule.
        self.phase_b = Phase.objects.create(
            job=self.job_b, title="Other Phase", status=PhaseStatuses.PENDING_SCHED
        )

        self.scheduler = User.objects.create_user(email="sched@test.com", password="pw12345")
        self.user_a = User.objects.create_user(email="ua@test.com", password="pw12345")
        self.user_b = User.objects.create_user(email="ub@test.com", password="pw12345")
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.scheduler)
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.user_a)
        OrganisationalUnitMember.objects.create(unit=self.unit_b, member=self.user_b)
        # Direct perms after the memberships (member save re-syncs unit perms).
        assign_perm("jobtracker.can_schedule_job", self.scheduler, self.unit)
        self.scheduler = _reload(self.scheduler)

    def _fmt(self, dt):
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _req(self, path, params=None, data=None):
        req = self.rf.post(path + ("?" + params if params else ""), data or {})
        req.user = self.scheduler
        return req

    def test_create_rejects_phase_from_another_job(self):
        from django.http import Http404

        req = self._req(
            "/scheduler/timeslot/create/phase",
            "job={}&phase={}&resource_id={}".format(self.job.pk, self.phase_b.pk, self.user_a.pk),
        )
        with self.assertRaises(Http404):
            sched_views.create_scheduler_phase_slot(req)

    def test_create_without_job_rejects_foreign_phase(self):
        req = self._req(
            "/scheduler/timeslot/create/phase",
            "resource_id={}".format(self.user_a.pk),
            {
                "user": self.user_a.pk,
                "phase": self.phase_b.pk,
                "deliveryRole": TimeSlotDeliveryRole.DELIVERY,
                "start": self._fmt(self.start),
                "end": self._fmt(self.end),
            },
        )
        with self.assertRaises(PermissionDenied):
            sched_views.create_scheduler_phase_slot(req)
        self.assertFalse(TimeSlot.objects.filter(phase=self.phase_b).exists())

    def test_edit_rejects_move_to_foreign_phase(self):
        slot = self._delivery_slot(user=self.user_a)
        req = self._req(
            "/scheduler/timeslot/change/{}".format(slot.pk),
            data={
                "user": self.user_a.pk,
                "phase": self.phase_b.pk,
                "deliveryRole": TimeSlotDeliveryRole.DELIVERY,
                "start": self._fmt(self.start),
                "end": self._fmt(self.end),
            },
        )
        with self.assertRaises(PermissionDenied):
            sched_views.change_scheduler_slot(req, pk=slot.pk)
        slot.refresh_from_db()
        self.assertEqual(slot.phase_id, self.phase.pk)

    def test_drag_rejects_internal_slot_onto_foreign_user(self):
        slot = self._internal_slot(user=self.user_a)
        req = self._req(
            "/scheduler/timeslot/change/{}/date".format(slot.pk),
            data={
                "user": self.user_b.pk,
                "start": self._fmt(self.start),
                "end": self._fmt(self.end),
            },
        )
        with self.assertRaises(PermissionDenied):
            sched_views.change_scheduler_slot_date(req, pk=slot.pk)
        slot.refresh_from_db()
        self.assertEqual(slot.user_id, self.user_a.pk)

    def test_drag_within_unit_still_allowed(self):
        slot = self._internal_slot(user=self.user_a)
        new_end = self.end + timedelta(hours=1)
        req = self._req(
            "/scheduler/timeslot/change/{}/date".format(slot.pk),
            data={
                "user": self.user_a.pk,
                "start": self._fmt(self.start),
                "end": self._fmt(new_end),
            },
        )
        resp = sched_views.change_scheduler_slot_date(req, pk=slot.pk)
        self.assertTrue(json.loads(resp.content)["form_is_valid"])


class DeltaFilterUnitTests(ScheduleHistoryBase):
    def test_filter_delta_for_users_none_is_passthrough(self):
        delta = {"upserts": [{"userId": 1}, {"userId": 2}], "removals": []}
        self.assertEqual(schedule_history.filter_delta_for_users(delta, None), delta)

    def test_filter_delta_for_users_restricts_upserts(self):
        delta = {"upserts": [{"userId": 1}, {"userId": 2}], "removals": [{"id": 9}]}
        out = schedule_history.filter_delta_for_users(delta, {2})
        self.assertEqual(out["upserts"], [{"userId": 2}])
        self.assertEqual(out["removals"], [{"id": 9}])
