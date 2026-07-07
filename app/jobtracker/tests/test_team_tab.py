from datetime import timedelta

from django.test import override_settings

from jobtracker.views.scheduler import (
    get_user_schedule_breakdown,
    get_user_phase_breakdown,
    build_team_rows,
)
from jobtracker.schedule_export import build_team_xlsx
from jobtracker.enums import TimeSlotDeliveryRole
from .test_schedule_history import ScheduleHistoryBase


# Creating/saving TimeSlots broadcasts schedule deltas over Channels; use the
# in-memory layer so tests don't block on the configured Redis channel layer.
@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class TeamBreakdownDatesTests(ScheduleHistoryBase):
    def test_breakdown_includes_start_and_end_dates(self):
        # Two delivery slots on different days -> min/max span should be captured.
        from jobtracker.models import TimeSlot

        self._delivery_slot()
        TimeSlot.objects.create(
            user=self.actor,
            slot_type=self.delivery_type,
            phase=self.phase,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=self.start + timedelta(days=2),
            end=self.end + timedelta(days=2),
        )
        breakdown = get_user_schedule_breakdown(self.job)
        entry = next(e for e in breakdown if e["user"] == self.actor)
        self.assertIsNotNone(entry["start"])
        self.assertIsNotNone(entry["end"])
        self.assertEqual(entry["start"], self.start)
        self.assertEqual(entry["end"], self.end + timedelta(days=2))

    def test_unscheduled_assignee_has_none_dates(self):
        # account_manager is assigned but has no booked slots.
        breakdown = get_user_schedule_breakdown(self.job)
        entry = next(e for e in breakdown if e["unscheduled"])
        self.assertIsNone(entry["start"])
        self.assertIsNone(entry["end"])

    def test_build_team_rows_aligns_capacities(self):
        self._delivery_slot()
        labels, entries = build_team_rows(get_user_schedule_breakdown(self.job))
        self.assertEqual(labels[0], "Delivery")
        scheduled = next(e for e in entries if not e["unscheduled"])
        # capacities aligns 1:1 with labels; the Delivery cell should be populated.
        self.assertEqual(len(scheduled["capacities"]), len(labels))
        self.assertIsNotNone(scheduled["capacities"][0])
        self.assertGreater(scheduled["capacities"][0]["days"], 0)


class TeamPhaseBreakdownTests(ScheduleHistoryBase):
    def test_phase_breakdown_splits_by_phase(self):
        from jobtracker.models import Phase, TimeSlot

        # Second phase with its own delivery slot for the same user.
        phase2 = Phase.objects.create(job=self.job, title="Phase 2")
        self._delivery_slot()  # phase 1
        TimeSlot.objects.create(
            user=self.actor,
            slot_type=self.delivery_type,
            phase=phase2,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=self.start,
            end=self.end,
        )
        pb = get_user_phase_breakdown(self.job)
        rows = pb[self.actor.pk]
        self.assertEqual(len(rows), 2)
        phase_ids = {r["phase"].pk for r in rows}
        self.assertEqual(phase_ids, {self.phase.pk, phase2.pk})

    def test_build_team_rows_attaches_phase_rows(self):
        self._delivery_slot()
        labels, entries = build_team_rows(
            get_user_schedule_breakdown(self.job), get_user_phase_breakdown(self.job)
        )
        scheduled = next(e for e in entries if not e["unscheduled"])
        self.assertTrue(scheduled["phase_rows"])
        prow = scheduled["phase_rows"][0]
        self.assertEqual(len(prow["capacities"]), len(labels))
        self.assertEqual(prow["phase"], self.phase)

    def test_phase_row_carries_phase_specific_roles(self):
        # actor leads the phase; the role must appear against the phase row.
        self.phase.project_lead = self.actor
        self.phase.save()
        self._delivery_slot()
        pb = get_user_phase_breakdown(self.job)
        prow = pb[self.actor.pk][0]
        self.assertIn("Lead", prow["assigned_roles"])

    def test_assigned_but_unbooked_phase_shows_as_unscheduled_row(self):
        # actor is Author on a phase with no booked hours -> row present, flagged.
        self.phase.report_author = self.actor
        self.phase.save()
        pb = get_user_phase_breakdown(self.job)
        rows = pb[self.actor.pk]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["unscheduled"])
        self.assertIn("Author", rows[0]["assigned_roles"])
        self.assertEqual(rows[0]["total_days"], 0)


class TeamExportTests(ScheduleHistoryBase):
    def test_job_team_export_smoke(self):
        self._delivery_slot()
        resp = build_team_xlsx(self.job)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertIn("team-", resp["Content-Disposition"])
        self.assertTrue(resp.content[:2] == b"PK")  # xlsx is a zip

    def test_phase_team_export_smoke(self):
        self._delivery_slot()
        resp = build_team_xlsx(self.job, self.phase)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content[:2] == b"PK")
