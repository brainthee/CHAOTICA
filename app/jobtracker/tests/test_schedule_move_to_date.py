"""T-08: "move to a start date" re-lays a schedule in working days.

The earliest slot lands on the new start date (or the person's next working
day); every slot keeps its offset and length counted in working days, so
weekends and holidays are skipped. "By days" mode is unchanged.
"""
import json
from datetime import date, datetime, time, timedelta

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import Holiday
from jobtracker import schedule_history
from jobtracker.enums import DefaultTimeSlotTypes, PhaseStatuses, TimeSlotDeliveryRole
from jobtracker.models import (
    OrganisationalUnitMember,
    Phase,
    ScheduleAction,
    TimeSlot,
    TimeSlotType,
)
from .test_schedule_history import ScheduleHistoryBase

# 2027-01-04 is a Monday.
MON = date(2027, 1, 4)


def _d(offset):
    return MON + timedelta(days=offset)


def _dt(day, h):
    return timezone.make_aware(datetime.combine(day, time(h, 0)))


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class MoveToDateTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        Phase.objects.filter(pk=self.phase.pk).update(status=PhaseStatuses.PENDING_SCHED)
        self.phase.refresh_from_db()
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.other)
        self.http = Client(HTTP_HOST="localhost")
        self.http.force_login(self.actor)  # superuser

    def _slot(self, first, last=None, user=None, phase=None, slot_type=None):
        last = first if last is None else last
        return TimeSlot.objects.create(
            user=user or self.other,
            slot_type=slot_type or self.delivery_type,
            phase=phase or self.phase if slot_type is None else None,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=_dt(first, 9),
            end=_dt(last, 17),
        )

    def _move(self, new_start, url=None, **extra):
        url = url or reverse(
            "phase_schedule_shift",
            kwargs={"job_slug": self.job.slug, "slug": self.phase.slug},
        )
        payload = {"mode": "to_date", "new_start": new_start.isoformat()}
        payload.update(extra)
        return json.loads(self.http.post(url, payload).content)

    def _days(self, slot):
        slot.refresh_from_db()
        return (timezone.localtime(slot.start).date(), timezone.localtime(slot.end).date())

    def test_spacing_kept_across_weekend(self):
        fri = self._slot(_d(4))  # Fri
        mon = self._slot(_d(7))  # next Mon: 1 working day later
        data = self._move(_d(9))  # Wed
        self.assertTrue(data["form_is_valid"], data)
        self.assertEqual(self._days(fri), (_d(9), _d(9)))  # Wed
        self.assertEqual(self._days(mon), (_d(10), _d(10)))  # Thu
        fri.refresh_from_db()
        self.assertEqual(timezone.localtime(fri.start).time(), time(9, 0))
        self.assertEqual(timezone.localtime(fri.end).time(), time(17, 0))

    def test_holiday_skipped(self):
        Holiday.objects.create(date=_d(10), reason="Test holiday")  # Thu, global
        first = self._slot(_d(4))
        second = self._slot(_d(7))
        self.assertTrue(self._move(_d(9))["form_is_valid"])
        self.assertEqual(self._days(first), (_d(9), _d(9)))  # Wed
        self.assertEqual(self._days(second), (_d(11), _d(11)))  # Fri (Thu is a holiday)

    def test_multi_day_slot_keeps_working_day_length(self):
        # Thu -> next Tue = Thu, Fri, Mon, Tue = 4 working days.
        slot = self._slot(_d(3), _d(8))
        self.assertTrue(self._move(_d(14))["form_is_valid"])  # Mon
        self.assertEqual(self._days(slot), (_d(14), _d(17)))  # Mon -> Thu

    def test_weekend_start_snaps_to_next_working_day(self):
        slot = self._slot(_d(1))
        self.assertTrue(self._move(_d(12))["form_is_valid"])  # Sat
        self.assertEqual(self._days(slot), (_d(14), _d(14)))  # Mon

    def test_locked_phases_skipped(self):
        locked = Phase.objects.create(job=self.job, title="Done")
        open_slot = self._slot(_d(0))
        locked_slot = self._slot(_d(1), phase=locked)
        Phase.objects.filter(pk=locked.pk).update(status=PhaseStatuses.DELIVERED)
        url = reverse("job_schedule_shift", kwargs={"slug": self.job.slug})
        self.assertTrue(self._move(_d(14), url=url)["form_is_valid"])
        self.assertEqual(self._days(open_slot), (_d(14), _d(14)))
        self.assertEqual(self._days(locked_slot), (_d(1), _d(1)))

    def test_overlap_warns_then_force_applies(self):
        slot = self._slot(_d(0))
        clash = self._slot(_d(14), user=self.other, slot_type=TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.UNASSIGNED
        ))
        data = self._move(_d(14))
        self.assertFalse(data["form_is_valid"])
        self.assertTrue(data["logic_checks_failed"])
        self.assertTrue(data["logic_checks_can_bypass"])
        self.assertEqual(self._days(slot), (_d(0), _d(0)))
        data = self._move(_d(14), force="1", override_reason="agreed")
        self.assertTrue(data["form_is_valid"])
        self.assertEqual(self._days(slot), (_d(14), _d(14)))
        action = ScheduleAction.objects.latest("created")
        self.assertTrue(action.forced)
        self.assertEqual(action.override_reason, "agreed")
        self.assertIn("Moved schedule to start", action.summary)
        self.assertTrue(TimeSlot.objects.filter(pk=clash.pk).exists())

    def test_overlap_with_leave_blocks(self):
        self._slot(_d(0))
        self._slot(_d(14), slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.LEAVE))
        data = self._move(_d(14), force="1")
        self.assertFalse(data["form_is_valid"])
        self.assertFalse(data["logic_checks_can_bypass"])

    def test_undo_restores_original_dates(self):
        a = self._slot(_d(4))
        b = self._slot(_d(7), _d(8))
        originals = {s.pk: (s.start, s.end) for s in (a, b)}
        self.assertTrue(self._move(_d(21))["form_is_valid"])
        action = ScheduleAction.objects.latest("created")
        self.assertEqual(action.action_type, "MOVE")
        schedule_history.revert(action, self.actor)
        for s in (a, b):
            s.refresh_from_db()
            self.assertEqual((s.start, s.end), originals[s.pk])

    def test_by_days_mode_unchanged(self):
        slot = self._slot(_d(4))  # Fri
        url = reverse(
            "phase_schedule_shift",
            kwargs={"job_slug": self.job.slug, "slug": self.phase.slug},
        )
        data = json.loads(self.http.post(
            url, {"mode": "days", "direction": "forward", "days": "1"}
        ).content)
        self.assertTrue(data["form_is_valid"])
        self.assertEqual(self._days(slot), (_d(5), _d(5)))  # Sat: calendar days
        # No ``mode`` at all means "by days" too.
        data = json.loads(self.http.post(
            url, {"direction": "back", "days": "1"}
        ).content)
        self.assertTrue(data["form_is_valid"])
        self.assertEqual(self._days(slot), (_d(4), _d(4)))

    def test_to_date_requires_date(self):
        url = reverse(
            "phase_schedule_shift",
            kwargs={"job_slug": self.job.slug, "slug": self.phase.slug},
        )
        data = json.loads(self.http.post(url, {"mode": "to_date"}).content)
        self.assertFalse(data["form_is_valid"])
