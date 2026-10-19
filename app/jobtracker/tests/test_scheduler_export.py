"""Tests for the global scheduler XLSX export (toolbar Export button)."""
import io
import json
from datetime import timedelta

from django.test import RequestFactory
from rest_framework.test import APIClient
from guardian.shortcuts import assign_perm
from openpyxl import load_workbook

from chaotica_utils.models import User
from jobtracker.enums import DefaultTimeSlotTypes, TimeSlotDeliveryRole
from jobtracker.models import (
    Client,
    Job,
    OrganisationalUnit,
    OrganisationalUnitMember,
    Phase,
    Project,
    TimeSlot,
    TimeSlotType,
)
from jobtracker.schedule_export import SCHEDULER_EXPORT_MAX_DAYS
from jobtracker.views import scheduler as sched_views
from .test_schedule_history import ScheduleHistoryBase


def v1_get(user, path, params):
    """The scheduler's read feeds are /api/v1/ now."""
    client = APIClient(HTTP_HOST="testserver")
    client.force_authenticate(user)
    resp = client.get(path, params)
    assert resp.status_code == 200, resp.content
    return resp.json()


def v1_window(start, end):
    return {"start": start.date().isoformat(), "end": end.date().isoformat()}


def v1_slot_rows(user, start, end, params):
    """/api/v1/schedule/ slots, with the old feed's key names for phase/type."""
    body = v1_get(user, "/api/v1/schedule/", {**v1_window(start, end), **params})
    return [
        {**row, "phaseId": row["phase"], "slot_type_ID": row["slot_type"]}
        for row in body["timeslots"]
    ]


class SchedulerScopeBase(ScheduleHistoryBase):
    """actor + other share a unit the actor may view; hidden sits in another."""

    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        # User.save() promotes the only user to superuser + Global Admin; on a
        # freshly flushed DB (just guardian's AnonymousUser) that's the actor.
        # Scope tests need an ordinary user, so demote explicitly.
        self.actor.is_superuser = self.actor.is_staff = False
        self.actor.first_name, self.actor.last_name = "Ada", "Actor"
        self.actor.save()
        self.actor.groups.clear()
        self.other.first_name, self.other.last_name = "Olly", "Other"
        self.other.save()
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.actor)
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.other)
        # Someone in a unit the actor can't see the schedule of.
        self.hidden = User.objects.create_user(
            email="hidden@test.com", password="pw12345", first_name="Hal", last_name="Hidden"
        )
        self.hidden_unit = OrganisationalUnit.objects.create(name="Hidden Unit")
        OrganisationalUnitMember.objects.create(unit=self.hidden_unit, member=self.hidden)
        assign_perm("jobtracker.view_users_schedule", self.actor, self.unit)
        self._reload_actor()

    def _reload_actor(self):
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


class SchedulerExportTests(SchedulerScopeBase):
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

    def test_rows_feed(self):
        # The scheduler's rows come from scheduler_member_rows via /api/v1/.
        data = v1_get(
            self.actor, "/api/v1/schedule/resources/", v1_window(self.start, self.end)
        )["users"]
        self.assertEqual({r["id"] for r in data}, {self.actor.pk, self.other.pk})
        self.assertTrue(all(r["display"] for r in data))


class HiddenWorkBase(SchedulerScopeBase):
    """Adds a job, phase and project in the hidden unit, all booked for hidden."""

    def setUp(self):
        super().setUp()
        self.hidden_job = Job.objects.create(
            unit=self.hidden_unit, client=Client.objects.create(name="Hidden Client"),
            title="Hidden Job", created_by=self.hidden, account_manager=self.hidden,
        )
        self.hidden_phase = Phase.objects.create(job=self.hidden_job, title="Hidden Phase")
        TimeSlot.objects.create(
            user=self.hidden, slot_type=self.delivery_type, phase=self.hidden_phase,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY, start=self.start, end=self.end,
        )
        self.hidden_project = Project.objects.create(
            title="Hidden Project", unit=self.hidden_unit, created_by=self.hidden
        )
        TimeSlot.objects.create(
            user=self.hidden, project=self.hidden_project, start=self.start, end=self.end,
            slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.INTERNAL_PROJECT),
        )

    def _member_ids(self, params, user=None):
        query = {**v1_window(self.start, self.end), **params}
        rows = v1_get(user or self.actor, "/api/v1/schedule/resources/", query)
        return {r["id"] for r in rows["users"]}


class SchedulerFilterScopeTests(HiddenWorkBase):
    """Query-string filters must never widen the global scheduler beyond the
    viewer's view_users_schedule scope (shared by the feeds and the export)."""

    def test_include_user_cannot_add_out_of_scope_user(self):
        ids = self._member_ids({"include_user": [str(self.hidden.pk)]})
        self.assertNotIn(self.hidden.pk, ids)
        wb = self._workbook(self._export({"include_user": [str(self.hidden.pk)]}))
        self.assertNotIn(self.hidden.get_full_name(), self._resources(wb))

    def test_include_user_still_adds_in_scope_user(self):
        ids = self._member_ids({
            "users": [str(self.actor.pk)], "include_user": [str(self.other.pk)],
        })
        self.assertEqual(ids, {self.actor.pk, self.other.pk})

    def test_job_filter_on_unviewable_job_hides_team(self):
        ids = self._member_ids({"jobs": [str(self.hidden_job.pk)]})
        self.assertNotIn(self.hidden.pk, ids)

    def test_job_filter_on_viewable_job_shows_whole_team(self):
        assign_perm("jobtracker.view_job_schedule", self.actor, self.hidden_unit)
        self._reload_actor()
        ids = self._member_ids({"jobs": [str(self.hidden_job.pk)]})
        self.assertIn(self.hidden.pk, ids)

    def test_phase_filter_on_unviewable_phase_hides_team(self):
        ids = self._member_ids({"phases": [str(self.hidden_phase.pk)]})
        self.assertNotIn(self.hidden.pk, ids)

    def test_project_filter_respects_view_project(self):
        params = {"projects": [str(self.hidden_project.pk)]}
        self.assertNotIn(self.hidden.pk, self._member_ids(params))
        assign_perm("jobtracker.view_project", self.actor)
        self._reload_actor()
        self.assertIn(self.hidden.pk, self._member_ids(params))


class SchedulerClientFilterTests(HiddenWorkBase):
    """Clients filter: people booked on the client's jobs, other work faded."""

    def setUp(self):
        super().setUp()
        self._delivery_slot()  # actor on self.job (Test Client); other has nothing

    def _slots(self, params):
        return v1_slot_rows(
            self.actor,
            self.start - timedelta(days=1),
            self.end + timedelta(days=1),
            params,
        )

    def _delivery_rows(self, params):
        return [r for r in self._slots(params) if r.get("phaseId") == self.phase.pk]

    def test_client_filter_shows_only_people_booked_for_client(self):
        ids = self._member_ids({"clients": [str(self.client_obj.pk)]})
        self.assertEqual(ids, {self.actor.pk})

    def test_client_filter_does_not_fade_its_own_work(self):
        rows = self._delivery_rows({"clients": [str(self.client_obj.pk)]})
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].get("out_of_scope"))

    def test_other_clients_work_is_faded(self):
        other_client = Client.objects.create(name="Elsewhere Ltd")
        rows = self._delivery_rows({
            "clients": [str(other_client.pk)], "include_user": [str(self.actor.pk)],
        })
        self.assertTrue(rows[0].get("out_of_scope"))
        self.assertNotEqual(rows[0].get("display"), "background")

    def test_client_filter_respects_job_schedule_permission(self):
        params = {"clients": [str(self.hidden_job.client.pk)]}
        self.assertNotIn(self.hidden.pk, self._member_ids(params))
        assign_perm("jobtracker.view_job_schedule", self.actor, self.hidden_unit)
        self._reload_actor()
        self.assertIn(self.hidden.pk, self._member_ids(params))

    def test_deleted_jobs_are_ignored(self):
        from jobtracker.enums import JobStatuses

        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.DELETED)
        ids = self._member_ids({"clients": [str(self.client_obj.pk)]})
        self.assertNotIn(self.actor.pk, ids)

    def test_export_mutes_slots_outside_client(self):
        other_client = Client.objects.create(name="Elsewhere Ltd")
        wb = self._workbook(self._export({
            "clients": [str(other_client.pk)], "include_user": [str(self.actor.pk)],
        }))
        overview = " ".join(
            str(c.value) for row in wb["Overview"].iter_rows() for c in row if c.value
        )
        self.assertIn("Elsewhere Ltd", overview)
        ws = wb["Schedule"]
        row = self._resources(wb).index(self.actor.get_full_name()) + 2
        booked = [c for c in ws[row] if c.value and "Phase 1" in str(c.value)]
        self.assertTrue(booked)
        self.assertEqual(booked[0].fill.fgColor.rgb[-6:].lower(), "eff2f6")  # muted

    def test_form_offers_only_viewable_clients(self):
        from jobtracker.forms import SchedulerFilter

        form = SchedulerFilter({}, user=self.actor)
        self.assertNotIn(self.client_obj, form.fields["clients"].queryset)
        assign_perm("jobtracker.view_client", self.actor)
        self._reload_actor()
        form = SchedulerFilter({}, user=self.actor)
        self.assertIn(self.client_obj, form.fields["clients"].queryset)


class SchedulerFocusTests(HiddenWorkBase):
    """Unhighlighted slots: faded on screen, hideable, and never "available"."""

    def setUp(self):
        super().setUp()
        self.focused = self._delivery_slot()  # actor, Test Client
        # Actor's other commitments: an internal slot on day+2, a project on day+3.
        self.internal = TimeSlot.objects.create(
            user=self.actor, slot_type=self.internal_type,
            start=self.start + timedelta(days=2), end=self.end + timedelta(days=2),
        )
        self.project = Project.objects.create(
            title="Side Project", unit=self.unit, created_by=self.actor
        )
        self.project_slot = TimeSlot.objects.create(
            user=self.actor, project=self.project,
            slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.INTERNAL_PROJECT),
            start=self.start + timedelta(days=3), end=self.end + timedelta(days=3),
        )
        self.client_params = {"clients": [str(self.client_obj.pk)]}

    def _slot_rows(self, params):
        return v1_slot_rows(
            self.actor,
            self.start - timedelta(days=1),
            self.end + timedelta(days=6),
            params,
        )

    def _by_id(self, rows):
        return {r["id"]: r for r in rows if isinstance(r.get("id"), int) and "slot_type_ID" in r}

    def test_everything_outside_the_focus_is_faded_not_backgrounded(self):
        rows = self._by_id(self._slot_rows(self.client_params))
        self.assertFalse(rows[self.focused.pk].get("out_of_scope"))
        for slot in (self.internal, self.project_slot):
            self.assertTrue(rows[slot.pk].get("out_of_scope"), slot)
            self.assertNotEqual(rows[slot.pk].get("display"), "background")

    def test_selected_project_is_in_focus(self):
        rows = self._by_id(self._slot_rows({"projects": [str(self.project.pk)]}))
        self.assertFalse(rows[self.project_slot.pk].get("out_of_scope"))
        self.assertTrue(rows[self.focused.pk].get("out_of_scope"))

    def test_no_focus_filter_fades_nothing(self):
        rows = self._by_id(self._slot_rows({}))
        self.assertFalse(any(r.get("out_of_scope") for r in rows.values()))

    def test_unfocused_days_are_never_shaded_available(self):
        from constance.test import override_config

        with override_config(SCHEDULE_SHADE_AVAILABLE=True):
            body = v1_get(
                self.actor,
                "/api/v1/schedule/",
                {
                    **v1_window(self.start - timedelta(days=1), self.end + timedelta(days=6)),
                    **self.client_params,
                },
            )
        avail = next(
            a["runs"] for a in body["availability"] if a["user"] == self.actor.pk
        )
        self.assertTrue(avail, "expected some available-day shading in the window")
        shaded = set()
        for r in avail:
            from datetime import date
            d = date.fromisoformat(str(r["start"])[:10])
            while d < date.fromisoformat(str(r["end"])[:10]):
                shaded.add(d)
                d += timedelta(days=1)
        for slot in (self.focused, self.internal, self.project_slot):
            self.assertNotIn(slot.start.date(), shaded, slot)

    def _grid_cell(self, wb, slot):
        ws = wb["Schedule"]
        row = self._resources(wb).index(self.actor.get_full_name()) + 2
        for col in range(6, ws.max_column + 1):
            if ws.cell(row=1, column=col).value.date() == slot.start.date():
                return ws.cell(row=row, column=col)

    def test_clean_export_hides_unfocused_but_marks_days_unavailable(self):
        wb = self._workbook(self._export(dict(self.client_params, hide_unfocused="1")))
        self.assertEqual(self._grid_cell(wb, self.internal).value, "Unavailable")
        self.assertEqual(self._grid_cell(wb, self.project_slot).value, "Unavailable")
        self.assertIn("Phase 1", str(self._grid_cell(wb, self.focused).value))
        bookings = wb["Bookings"]
        self.assertEqual(bookings.max_row, 2)  # just the focused slot
        overview = " ".join(
            str(c.value) for row in wb["Overview"].iter_rows() for c in row if c.value
        )
        self.assertIn("HIDDEN", overview)

    def test_export_without_hide_keeps_unfocused_slots(self):
        wb = self._workbook(self._export(self.client_params))
        self.assertEqual(wb["Bookings"].max_row, 4)
        self.assertNotEqual(self._grid_cell(wb, self.project_slot).value, "Unavailable")

    def test_hide_flag_ignored_without_focus_filter(self):
        wb = self._workbook(self._export({"hide_unfocused": "1"}))
        self.assertEqual(wb["Bookings"].max_row, 4)


class ProfileScheduleExportTests(SchedulerScopeBase):
    """T-11: export one person's schedule from their profile."""

    def _profile_export(self, person, viewer, method="post"):
        from django.test import Client
        from django.urls import reverse

        http = Client(HTTP_HOST="localhost")
        http.force_login(User.objects.get(pk=viewer.pk))
        url = reverse("user_schedule_export", kwargs={"email": person.email})
        if method == "get":
            return http.get(url)
        return http.post(url, {
            "start": (self.start - timedelta(days=7)).date().isoformat(),
            "end": (self.end + timedelta(days=7)).date().isoformat(),
        })

    def test_unit_schedule_viewer_can_export_only_that_person(self):
        self._delivery_slot(user=self.other)
        self._delivery_slot(user=self.actor)
        wb = self._workbook(self._profile_export(self.other, self.actor))
        self.assertEqual(self._resources(wb), [self.other.get_full_name()])
        bookings = wb["Bookings"]
        self.assertEqual(bookings.max_row, 2)
        self.assertEqual(bookings.cell(row=2, column=1).value, self.other.get_full_name())

    def test_self_can_export(self):
        wb = self._workbook(self._profile_export(self.hidden, self.hidden))
        self.assertEqual(self._resources(wb), [self.hidden.get_full_name()])

    def test_manager_can_export(self):
        self.hidden.manager = self.other
        self.hidden.save()
        wb = self._workbook(self._profile_export(self.hidden, self.other))
        self.assertEqual(self._resources(wb), [self.hidden.get_full_name()])

    def test_stranger_gets_403(self):
        self.assertEqual(self._profile_export(self.hidden, self.actor).status_code, 403)
        self.assertEqual(
            self._profile_export(self.hidden, self.actor, method="get").status_code, 403
        )

    def test_deactivated_person_can_still_be_exported(self):
        self.other.is_active = False
        self.other.save()
        wb = self._workbook(self._profile_export(self.other, self.actor))
        self.assertEqual(self._resources(wb), [self.other.get_full_name()])

    def test_get_returns_modal(self):
        resp = self._profile_export(self.other, self.actor, method="get")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Download XLSX", json.loads(resp.content)["html_form"])

    def test_profile_hides_schedule_tab_without_access(self):
        from django.test import Client
        from django.urls import reverse

        from django.conf import settings
        from chaotica_utils.enums import GlobalRoles
        from chaotica_utils.models import Group

        # The profile page needs a global role (the base fixture demotes actor).
        group, _ = Group.objects.get_or_create(
            name=settings.GLOBAL_GROUP_PREFIX + GlobalRoles.CHOICES[GlobalRoles.USER][1]
        )
        self.actor.groups.add(group)
        http = Client(HTTP_HOST="localhost")
        http.force_login(self.actor)
        resp = http.get(reverse("user_profile", kwargs={"email": self.hidden.email}))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_view_schedule"])
        self.assertNotContains(resp, 'id="schedule-tab"')
        self.assertNotContains(resp, "Export schedule")
        resp = http.get(reverse("user_profile", kwargs={"email": self.other.email}))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["can_view_schedule"])
        self.assertContains(resp, 'id="schedule-tab"')
        self.assertContains(resp, "Export schedule")

    def test_global_export_with_unknown_user_does_not_leak_everyone(self):
        self.other.is_active = False
        self.other.save()
        wb = self._workbook(self._export({"users": [str(self.other.pk)]}))
        self.assertEqual(self._resources(wb), [])
        wb = self._workbook(self._export({"users": ["999999"]}))
        self.assertEqual(self._resources(wb), [])
