"""Scheduler read (A5): windows, rows, scoped schedules, history, deltas."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import Holiday, User
from jobtracker.enums import DefaultTimeSlotTypes, JobStatuses, TimeSlotDeliveryRole
from jobtracker.models import ScheduleAction, TimeSlot, TimeSlotComment, TimeSlotType

from .helpers import ApiV1TestCase, make_member


def _monday():
    today = timezone.now().date()
    return today - timedelta(days=today.weekday()) + timedelta(days=7)


class ScheduleBase(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.job = self.make_job(status=JobStatuses.IN_PROGRESS)
        self.phase = self.make_phase(self.job, title="Infra")
        self.viewer = make_member(
            User.objects.create_user(email="sched@example.com", password="pw"),
            self.job.unit,
        )
        self.crew = make_member(
            User.objects.create_user(email="crew@example.com", password="pw"),
            self.job.unit,
        )
        # Someone in another unit the viewer can't see.
        other_job = self.make_job()
        self.stranger = make_member(
            User.objects.create_user(email="stranger@example.com", password="pw"),
            other_job.unit,
        )
        self.day = _monday()
        start = timezone.make_aware(
            timezone.datetime.combine(self.day, timezone.datetime.min.time())
        ) + timedelta(hours=9)
        self.slot = TimeSlot.objects.create(
            user=self.crew,
            phase=self.phase,
            slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY),
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=start,
            end=start + timedelta(hours=8),
        )
        self.stranger_slot = TimeSlot.objects.create(
            user=self.stranger,
            slot_type=TimeSlotType.get_builtin_object(
                DefaultTimeSlotTypes.INTERNAL_PROJECT
            ),
            start=start,
            end=start + timedelta(hours=8),
        )
        self.window = {
            "start": self.day.isoformat(),
            "end": (self.day + timedelta(days=4)).isoformat(),
        }
        self.api = self.as_user(self.viewer)


class ScheduleWindowTests(ScheduleBase):
    def test_refs_comments_availability(self):
        TimeSlotComment.objects.create(
            user=self.crew,
            start=self.slot.start,
            end=self.slot.end,
            comment="On site",
        )
        body = self.api.get("/api/v1/schedule/", self.window).json()
        self.phase.refresh_from_db()
        ref = body["refs"]["phases"][str(self.phase.pk)]
        self.assertEqual(ref["display"], f"{self.phase.phase_id} Infra")
        self.assertEqual([c["comment"] for c in body["comments"]], ["On site"])
        self.assertIsNone(body["scope"])
        runs = {a["user"]: a["runs"] for a in body["availability"]}
        # The booked Monday isn't available; the rest of the week is.
        self.assertEqual(
            runs[self.crew.pk][0]["start"], (self.day + timedelta(days=1)).isoformat()
        )
        slot_users = {s["user"] for s in body["timeslots"]}
        self.assertNotIn(self.stranger.pk, slot_users)

    def test_scheduler_filter_fields(self):
        body = self.api.get(
            "/api/v1/schedule/", {**self.window, "users": self.crew.pk}
        ).json()
        self.assertEqual({u["user"] for u in body["users"]}, {self.crew.pk})

    def test_filter_cannot_widen(self):
        body = self.api.get(
            "/api/v1/schedule/", {**self.window, "users": self.stranger.pk}
        ).json()
        self.assertEqual(body["users"], [])

    def test_global_holidays_included(self):
        Holiday.objects.create(date=self.day + timedelta(days=2), reason="Founders Day")
        body = self.api.get("/api/v1/schedule/", self.window).json()
        self.assertIn("Founders Day", {h["reason"] for h in body["holidays"]})

    def test_resources(self):
        body = self.api.get("/api/v1/schedule/resources/").json()
        ids = {u["id"] for u in body["users"]}
        self.assertTrue({self.viewer.pk, self.crew.pk} <= ids)
        self.assertNotIn(self.stranger.pk, ids)
        row = body["users"][0]
        self.assertEqual(row["type"], "user")
        self.assertIn("job_level_label", row)

    def test_comments_endpoint_scoped(self):
        TimeSlotComment.objects.create(
            user=self.stranger, start=self.slot.start, end=self.slot.end, comment="x"
        )
        mine = TimeSlotComment.objects.create(
            user=self.crew, start=self.slot.start, end=self.slot.end, comment="y"
        )
        rows = self.api.get("/api/v1/timeslot-comments/").json()["results"]
        self.assertEqual([r["id"] for r in rows], [mine.pk])


class ScopedScheduleTests(ScheduleBase):
    def test_job_schedule(self):
        body = self.api.get(f"/api/v1/jobs/{self.job.pk}/schedule/", self.window).json()
        self.assertEqual(body["scope"]["phase_ids"], [self.phase.pk])
        self.assertFalse(body["scope"]["hard"])
        self.assertIn(self.crew.pk, {u["user"] for u in body["users"]})

    def test_include_user_clamped(self):
        """Security: include_user used to add anyone, exposing their slots."""
        body = self.api.get(
            f"/api/v1/phases/{self.phase.pk}/schedule/",
            {**self.window, "include_user": self.stranger.pk},
        ).json()
        self.assertNotIn(self.stranger.pk, {u["user"] for u in body["users"]})
        body = self.api.get(
            f"/api/v1/phases/{self.phase.pk}/schedule/",
            {**self.window, "include_user": self.viewer.pk},
        ).json()
        self.assertIn(self.viewer.pk, {u["user"] for u in body["users"]})

    def test_legacy_job_feed_include_user_clamped(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(
            reverse("view_job_schedule_slots", kwargs={"slug": self.job.slug}),
            {
                "start": self.slot.start.isoformat(),
                "end": self.slot.end.isoformat(),
                "include_user": self.stranger.pk,
            },
        )
        self.assertEqual(resp.status_code, 200)
        ids = {item.get("id") for item in resp.json()}
        self.assertNotIn(f"slot-{self.stranger_slot.pk}", ids)
        self.assertNotIn(self.stranger_slot.pk, ids)


class HistoryTests(ScheduleBase):
    def setUp(self):
        super().setUp()
        self.visible = ScheduleAction.objects.create(
            actor=self.superuser,
            action_type="CREATE",
            job=self.job,
            phase=self.phase,
            summary="Created 1 slot",
            payload=[
                {
                    "model": "timeslot",
                    "pk": self.slot.pk,
                    "before": None,
                    "after": {"user_id": self.crew.pk},
                }
            ],
        )
        self.hidden = ScheduleAction.objects.create(
            actor=self.superuser,
            action_type="CREATE",
            summary="Created 1 slot",
            payload=[
                {
                    "model": "timeslot",
                    "pk": self.stranger_slot.pk,
                    "before": None,
                    "after": {"user_id": self.stranger.pk},
                }
            ],
        )

    def test_global_history_filtered_per_viewer(self):
        """Security: the global history used to list everyone's changes."""
        ids = {a["id"] for a in self.api.get("/api/v1/schedule/actions/").json()}
        self.assertIn(self.visible.pk, ids)
        self.assertNotIn(self.hidden.pk, ids)
        self.client.force_login(self.viewer)
        legacy = self.client.get(reverse("schedule_action_history")).json()["actions"]
        self.assertNotIn(self.hidden.pk, {a["id"] for a in legacy})

    def test_job_history(self):
        rows = self.api.get("/api/v1/schedule/actions/", {"job": self.job.pk}).json()
        self.assertEqual([a["id"] for a in rows], [self.visible.pk])
        self.assertEqual(rows[0]["items"][0]["change"], "added")
        self.assertEqual(rows[0]["actor"]["id"], self.superuser.pk)

    def test_deltas(self):
        self.assertEqual(self.api.get("/api/v1/schedule/deltas/").status_code, 400)
        since = (timezone.now() - timedelta(minutes=5)).isoformat()
        body = self.api.get("/api/v1/schedule/deltas/", {"since": since}).json()
        by_action = {d["action_id"]: d for d in body["deltas"]}
        self.assertEqual(
            [s["id"] for s in by_action[self.visible.pk]["timeslots"]], [self.slot.pk]
        )
        self.assertNotIn(self.hidden.pk, by_action)
