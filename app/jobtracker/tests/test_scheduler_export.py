"""Tests for the global scheduler XLSX export (toolbar Export button)."""
import io
import json
from datetime import timedelta

from django.test import RequestFactory
from guardian.shortcuts import assign_perm
from openpyxl import load_workbook

from chaotica_utils.models import User
from jobtracker.models import OrganisationalUnit, OrganisationalUnitMember
from jobtracker.schedule_export import SCHEDULER_EXPORT_MAX_DAYS
from jobtracker.views import scheduler as sched_views
from .test_schedule_history import ScheduleHistoryBase


class SchedulerExportTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        self.actor.first_name, self.actor.last_name = "Ada", "Actor"
        self.actor.save()
        self.other.first_name, self.other.last_name = "Olly", "Other"
        self.other.save()
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.actor)
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.other)
        # Someone in a unit the actor can't see the schedule of.
        self.hidden = User.objects.create_user(
            email="hidden@test.com", password="pw12345", first_name="Hal", last_name="Hidden"
        )
        hidden_unit = OrganisationalUnit.objects.create(name="Hidden Unit")
        OrganisationalUnitMember.objects.create(unit=hidden_unit, member=self.hidden)
        assign_perm("jobtracker.view_users_schedule", self.actor, self.unit)
        self.actor = User.objects.get(pk=self.actor.pk)  # reset perm cache

    def _export(self, params=None, user=None, start=None, end=None):
        query = {
            "start": (start or self.start - timedelta(days=7)).isoformat(),
            "end": (end or self.end + timedelta(days=7)).isoformat(),
        }
        query.update(params or {})
        req = self.rf.get("/jobtracker/scheduler/export", query)
        req.user = user or self.actor
        return sched_views.export_scheduler_view(req)

    def _workbook(self, resp):
        self.assertEqual(resp.status_code, 200, resp.content[:200])
        self.assertIn("attachment;", resp["Content-Disposition"])
        return load_workbook(io.BytesIO(resp.content))

    def _resources(self, wb):
        ws = wb["Schedule"]
        return [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]

    def test_export_has_all_sheets_and_visible_members_only(self):
        wb = self._workbook(self._export())
        self.assertEqual(wb.sheetnames, ["Overview", "Schedule", "Bookings", "Resources"])
        names = self._resources(wb)
        self.assertIn(self.actor.get_full_name(), names)
        self.assertIn(self.other.get_full_name(), names)  # nothing booked, still listed
        self.assertNotIn(self.hidden.get_full_name(), names)

    def test_grid_and_bookings_show_slot(self):
        slot = self._delivery_slot()
        wb = self._workbook(self._export())
        ws = wb["Schedule"]
        row = self._resources(wb).index(self.actor.get_full_name()) + 2
        cells = [c.value for c in ws[row] if c.value]
        self.assertTrue(any(slot.get_schedule_title() in str(v) for v in cells))
        bookings = wb["Bookings"]
        self.assertEqual(bookings.max_row, 2)
        self.assertEqual(bookings.cell(row=2, column=1).value, self.actor.get_full_name())
        self.assertEqual(bookings.cell(row=2, column=5).value, "{}: {}".format(self.job.id, self.job.title))

    def test_grid_spans_requested_range(self):
        start = self.start - timedelta(days=7)
        end = self.end + timedelta(days=7)
        ws = self._workbook(self._export(start=start, end=end))["Schedule"]
        meta_cols = 5
        days = (end.date() - start.date()).days + 1
        self.assertEqual(ws.max_column, meta_cols + days)

    def test_filter_is_applied(self):
        wb = self._workbook(self._export({"users": [str(self.other.pk)]}))
        self.assertEqual(self._resources(wb), [self.other.get_full_name()])
        overview = [c.value for row in wb["Overview"].iter_rows() for c in row if c.value]
        self.assertTrue(any(self.other.get_full_name() in str(v) for v in overview))

    def test_out_of_window_slot_excluded(self):
        self._delivery_slot()
        far = self.start + timedelta(days=60)
        wb = self._workbook(self._export(start=far, end=far + timedelta(days=7)))
        self.assertEqual(wb["Bookings"].max_row, 1)

    def test_missing_or_bad_range_is_400(self):
        req = self.rf.get("/jobtracker/scheduler/export", {"start": "nope"})
        req.user = self.actor
        self.assertEqual(sched_views.export_scheduler_view(req).status_code, 400)
        resp = self._export(start=self.end, end=self.start - timedelta(days=2))
        self.assertEqual(resp.status_code, 400)

    def test_range_cap(self):
        resp = self._export(end=self.start + timedelta(days=SCHEDULER_EXPORT_MAX_DAYS + 1))
        self.assertEqual(resp.status_code, 400)

    def test_members_feed_still_json(self):
        # Refactor guard: get_scheduler_members now wraps scheduler_member_rows.
        req = self.rf.get(
            "/jobtracker/scheduler/members",
            {"start": self.start.isoformat(), "end": self.end.isoformat()},
        )
        req.user = self.actor
        data = json.loads(sched_views.view_scheduler_members(req).content)
        self.assertEqual({r["id"] for r in data}, {self.actor.pk, self.other.pk})
        self.assertTrue(all(r["html_view"] for r in data))
