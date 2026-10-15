"""T-09: overridden scheduler warnings are recorded; override gaps fixed.

A save made past a bypassable warning ("Save anyway") marks its ScheduleAction
``forced`` (with the optional reason) and writes a warning-severity Activity Log
event. Edits / drags now run the create-path overlap check, a forced batch
still skips people on leave, a project booking onto leave says so, and a
destructive booking is fully undoable.
"""
import json
from datetime import timedelta

from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import AuditEvent, AuditSeverity
from jobtracker import schedule_history
from jobtracker.enums import DefaultTimeSlotTypes, PhaseStatuses, TimeSlotDeliveryRole
from jobtracker.models import Phase, Project, ScheduleAction, TimeSlot, TimeSlotType
from jobtracker.views import scheduler as sched_views
from .test_schedule_history import ScheduleHistoryBase


def _fmt(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class OverrideTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        Phase.objects.filter(pk=self.phase.pk).update(status=PhaseStatuses.PENDING_SCHED)
        self.phase.refresh_from_db()
        self.rf = RequestFactory()
        self.http = Client(HTTP_HOST="localhost")
        self.http.force_login(self.actor)  # superuser (first user)
        self.leave_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.LEAVE)
        self.project_type = TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.INTERNAL_PROJECT
        )
        self.project = Project.objects.create(
            title="Internal work", unit=self.unit, created_by=self.actor
        )
        base = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
        self.day = lambda n, h=9: base + timedelta(days=n, hours=h - 9)

    def _slot(self, day, slot_type=None, user=None, hours=8):
        slot_type = slot_type or self.delivery_type
        return TimeSlot.objects.create(
            user=user or self.other,
            slot_type=slot_type,
            phase=self.phase if slot_type == self.delivery_type else None,
            project=self.project if slot_type == self.project_type else None,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=self.day(day),
            end=self.day(day) + timedelta(hours=hours),
        )

    def _drag(self, slot, to_day, **extra):
        payload = {
            "user": slot.user_id,
            "start": _fmt(self.day(to_day)),
            "end": _fmt(self.day(to_day) + timedelta(hours=8)),
        }
        payload.update(extra)
        url = reverse("change_scheduler_slot_date", kwargs={"pk": slot.pk})
        return json.loads(self.http.post(url, payload).content)

    # ---- edits / drags warn about overlaps ----

    def test_drag_onto_booking_warns(self):
        moving = self._slot(1)
        self._slot(3)
        data = self._drag(moving, 3)
        self.assertFalse(data["form_is_valid"])
        self.assertTrue(data["logic_checks_failed"])
        self.assertTrue(data["logic_checks_can_bypass"])
        moving.refresh_from_db()
        self.assertEqual(moving.start, self.day(1))

    def test_forced_drag_records_override_with_reason(self):
        moving = self._slot(1)
        self._slot(3)
        data = self._drag(moving, 3, force="1", override_reason="Client asked")
        self.assertTrue(data["form_is_valid"])
        action = ScheduleAction.objects.latest("created")
        self.assertTrue(action.forced)
        self.assertEqual(action.override_reason, "Client asked")
        self.assertIn("overlap with 1 booking", action.summary)
        event = AuditEvent.objects.filter(severity=AuditSeverity.WARNING).latest("timestamp")
        self.assertIn("Warning overridden", event.message)
        self.assertIn("Client asked", event.message)
        self.assertEqual(event.metadata["reason"], "Client asked")
        self.assertEqual(event.category, "schedule")

    def test_forced_drag_without_reason(self):
        moving = self._slot(1)
        self._slot(3)
        data = self._drag(moving, 3, force="1")
        self.assertTrue(data["form_is_valid"])
        action = ScheduleAction.objects.latest("created")
        self.assertTrue(action.forced)
        self.assertEqual(action.override_reason, "")
        self.assertTrue(
            AuditEvent.objects.filter(
                severity=AuditSeverity.WARNING, message__startswith="Warning overridden"
            ).exists()
        )

    def test_force_zero_does_not_bypass(self):
        moving = self._slot(1)
        self._slot(3)
        data = self._drag(moving, 3, force="0")
        self.assertFalse(data["form_is_valid"])
        self.assertTrue(data["logic_checks_can_bypass"])

    def test_unforced_clean_move_not_marked(self):
        moving = self._slot(1)
        data = self._drag(moving, 5)
        self.assertTrue(data["form_is_valid"])
        self.assertFalse(ScheduleAction.objects.latest("created").forced)
        self.assertFalse(AuditEvent.objects.filter(severity=AuditSeverity.WARNING).exists())

    def test_existing_overlap_does_not_rewarn(self):
        # Already double-booked: nudging it (still overlapping the same slot)
        # isn't a new overlap.
        moving = self._slot(1)
        self._slot(1)
        payload = {
            "user": moving.user_id,
            "start": _fmt(self.day(1, 10)),
            "end": _fmt(self.day(1, 16)),
        }
        url = reverse("change_scheduler_slot_date", kwargs={"pk": moving.pk})
        data = json.loads(self.http.post(url, payload).content)
        self.assertTrue(data["form_is_valid"])

    def test_drag_onto_leave_blocks_even_forced(self):
        moving = self._slot(1)
        self._slot(3, slot_type=self.leave_type)
        data = self._drag(moving, 3, force="1")
        self.assertFalse(data["form_is_valid"])
        self.assertFalse(data["logic_checks_can_bypass"])

    # ---- batch / project create ----

    def _batch(self, users, force):
        req = self.rf.post("/x", {"override_reason": "batch reason"} if force else {})
        req.user = self.actor
        start, end = self.day(3), self.day(3) + timedelta(hours=8)

        def build(u):
            return TimeSlot(
                user=u, slot_type=self.project_type, project=self.project,
                start=start, end=end,
            )

        data = sched_views._run_batch_create(
            req, users, build, sched_views._evaluate_project_slot, force
        )
        sched_views._record_created(req, data)
        return data

    def test_forced_batch_still_skips_people_on_leave(self):
        self._slot(3, slot_type=self.leave_type, user=self.other)  # blocked
        self._slot(3, slot_type=self.project_type, user=self.actor)  # warning
        data = self._batch([self.other, self.actor], force=False)
        self.assertFalse(data["form_is_valid"])
        self.assertTrue(data["logic_checks_can_bypass"])
        data = self._batch([self.other, self.actor], force=True)
        self.assertTrue(data["form_is_valid"])
        self.assertIn("Skipped 1", data["summary"])
        self.assertFalse(
            TimeSlot.objects.filter(user=self.other, slot_type=self.project_type).exists()
        )
        self.assertEqual(
            TimeSlot.objects.filter(user=self.actor, slot_type=self.project_type).count(), 2
        )
        action = ScheduleAction.objects.latest("created")
        self.assertTrue(action.forced)
        self.assertEqual(action.override_reason, "batch reason")

    def test_project_create_onto_leave_gives_feedback(self):
        self._slot(3, slot_type=self.leave_type, user=self.other)
        data = self._batch([self.other], force=False)
        self.assertFalse(data["form_is_valid"])
        self.assertTrue(data["logic_checks_failed"])
        self.assertFalse(data["logic_checks_can_bypass"])
        self.assertTrue(data["logic_checks_feedback"])
        data = self._batch([self.other], force=True)
        self.assertFalse(data["form_is_valid"])
        self.assertFalse(
            TimeSlot.objects.filter(user=self.other, slot_type=self.project_type).exists()
        )

    # ---- destructive booking is undoable ----

    def test_destructive_booking_undo_restores_cleared_slots(self):
        existing = self._slot(2, hours=8)
        spanning = self._slot(1, hours=24 * 3)  # day 1 .. day 4: gets split
        before_ids = {existing.pk, spanning.pk}
        req = self.rf.post("/x", {"overlap_mode": "destructive", "override_reason": "swap"})
        req.user = self.actor
        base = TimeSlot(
            user=self.other, phase=self.phase, slot_type=self.delivery_type,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=self.day(2), end=self.day(2) + timedelta(hours=8),
        )
        data = sched_views._create_delivery_single(req, base, False)
        sched_views._record_created(req, data)
        self.assertTrue(data["form_is_valid"])
        self.assertFalse(TimeSlot.objects.filter(pk__in=before_ids).exists())
        action = ScheduleAction.objects.latest("created")
        self.assertTrue(action.forced)
        self.assertIn("cleared 2 bookings", action.summary)

        schedule_history.revert(action, self.actor)
        remaining = TimeSlot.objects.filter(user=self.other).order_by("start")
        self.assertEqual(
            [(s.start, s.end) for s in remaining],
            sorted([(spanning.start, spanning.end), (existing.start, existing.end)]),
        )
