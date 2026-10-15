"""Dashboard scoping tests.

Regression cover for the leak where consultants saw jobs/phases they had no part
in. The personal operational tabs (In Flight / Scheduled This Week / Upcoming
Reports) must only show phases the user is involved in unless they are a
people-manager or hold a job-oversight role; the Alarms tab must only go unit-wide
for job-oversight roles (QA/scope/deliver/signoff), never for a plain
people-manager.
"""

import json
from datetime import timedelta

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User
from jobtracker.models import (
    Client as JobClient,
    Job,
    OrganisationalUnit,
    OrganisationalUnitMember,
    Phase,
)
from jobtracker.alarms import STALE_KEYS
from jobtracker.enums import JobStatuses, PhaseStatuses


# Custom SessionMiddleware rejects requests without a valid HTTP_HOST.
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class DashboardScopingTests(TestCase):
    def setUp(self):
        # create_user promotes the very first user to superuser; make that one
        # explicit so the consultant stays unprivileged.
        self.superuser = User.objects.create_user(
            email="su@test.com", password="pw12345"
        )
        self.superuser.is_superuser = True
        self.superuser.save()

        self.unit = OrganisationalUnit.objects.create(name="Unit A")
        self.job_client = JobClient.objects.create(name="Acme")
        self.job = Job.objects.create(
            unit=self.unit,
            title="Some Job",
            client=self.job_client,
            created_by=self.superuser,
            account_manager=self.superuser,
            status=JobStatuses.IN_PROGRESS,
        )
        # Active, overdue, unscheduled phase led by the superuser (NOT the
        # consultant) — a delivery_overdue alarm candidate and an in_flight row.
        self.phase = Phase.objects.create(
            job=self.job,
            title="Some Phase",
            status=PhaseStatuses.IN_PROGRESS,
            project_lead=self.superuser,
            desired_delivery_date=timezone.now().date() - timedelta(days=5),
        )

        # A consultant who can view the unit's jobs (as the CONSULTANT role grants)
        # but is not scheduled/lead/author on the phase, and manages nobody. They
        # must be a unit member: the queue tabs only go unit-wide for units the
        # user belongs to. Membership is created first because its save() re-syncs
        # guardian perms from roles and would strip the direct grant below.
        self.consultant = User.objects.create_user(
            email="consultant@test.com", password="pw12345"
        )
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.consultant)
        assign_perm("jobtracker.can_view_jobs", self.consultant, self.unit)

    def _dashboard_context(self, user):
        """What each tab would show: the tabs load lazily (dashboard_tab), so
        gather their partials' lists into one dict keyed like the old index
        context."""
        # Re-fetch to clear guardian's per-instance permission cache.
        user = User.objects.get(pk=user.pk)
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)
        resp = client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)
        ctx = {}
        for key, name in [
            ("in_flight", "in_flight"),
            ("scheduled_this_week", "scheduled_phases_this_week"),
            ("upcoming_reports", "upcoming_reports"),
        ]:
            tab = client.get(reverse("dashboard_tab", args=[key]))
            self.assertEqual(tab.status_code, 200)
            ctx[name] = tab.context["items"]
        tab = client.get(reverse("dashboard_tab", args=["alarms"]))
        self.assertEqual(tab.status_code, 200)
        ctx["alarms"] = tab.context["alarms"]
        return ctx

    def test_uninvolved_consultant_sees_no_phase(self):
        ctx = self._dashboard_context(self.consultant)
        self.assertNotIn(self.phase, ctx["in_flight"])
        self.assertNotIn(self.phase, ctx["scheduled_phases_this_week"])
        self.assertNotIn(self.phase, ctx["upcoming_reports"])
        self.assertNotIn(self.phase, ctx["alarms"]["delivery_overdue"])

    def test_involved_consultant_sees_own_phase(self):
        self.phase.project_lead = self.consultant
        self.phase.save()
        ctx = self._dashboard_context(self.consultant)
        self.assertIn(self.phase, ctx["in_flight"])

    def test_people_manager_gets_operational_view_but_personal_alarms(self):
        # Managing someone makes them a people-manager: operational tabs go
        # unit-wide, but alarms stay personal (line-management is not unit
        # management, so it does not unlock the unit-wide alarm view).
        managed = User.objects.create_user(
            email="managed@test.com", password="pw12345"
        )
        managed.manager = self.consultant
        managed.save()

        ctx = self._dashboard_context(self.consultant)
        self.assertIn(self.phase, ctx["in_flight"])
        self.assertNotIn(self.phase, ctx["alarms"]["delivery_overdue"])

    def test_scoper_role_does_not_unlock_unit_alarms(self):
        # A scoper (can_scope/can_signoff, unit-wide by design) must NOT see
        # every unit alarm — scoping has its own dedicated queue tab.
        assign_perm("jobtracker.can_scope_jobs", self.consultant, self.unit)
        assign_perm("jobtracker.can_signoff_scopes", self.consultant, self.unit)
        ctx = self._dashboard_context(self.consultant)
        self.assertNotIn(self.phase, ctx["alarms"]["delivery_overdue"])

    def test_unit_manager_sees_all_unit_alarms(self):
        assign_perm("jobtracker.change_organisationalunit", self.consultant, self.unit)
        ctx = self._dashboard_context(self.consultant)
        self.assertIn(self.phase, ctx["alarms"]["delivery_overdue"])

    def test_tqa_role_sees_tqa_alarms_only_not_delivery(self):
        # A TQA-role holder sees TQA alarms unit-wide, but NOT delivery-overdue
        # alarms for phases they are not on the team of.
        tqa_phase = Phase.objects.create(
            job=self.job,
            title="TQA Phase",
            status=PhaseStatuses.PENDING_TQA,
            project_lead=self.superuser,
            desired_delivery_date=timezone.now().date() + timedelta(days=30),
            due_to_techqa_set=timezone.now().date() - timedelta(days=3),
        )
        assign_perm("jobtracker.can_tqa_jobs", self.consultant, self.unit)
        ctx = self._dashboard_context(self.consultant)
        self.assertIn(tqa_phase, ctx["alarms"]["tqa_overdue"])
        # self.phase is only delivery-overdue; the TQA role must not surface it.
        self.assertNotIn(self.phase, ctx["alarms"]["delivery_overdue"])


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class DashboardLazyTabTests(DashboardScopingTests):
    """T-12: tabs load on demand (``dashboard_tab``) and refresh themselves."""

    ALL_ROLES = [
        "can_scope_jobs", "can_signoff_scopes", "can_tqa_jobs", "can_pqa_jobs",
        "can_deliver_job", "change_organisationalunit",
    ]

    def _client(self, user):
        client = Client(HTTP_HOST="localhost")
        client.force_login(User.objects.get(pk=user.pk))
        return client

    def _grant_all(self):
        for perm in self.ALL_ROLES:
            assign_perm("jobtracker." + perm, self.consultant, self.unit)

    def test_every_tab_returns_html_and_matching_count(self):
        self._grant_all()
        from dashboard.views import DASHBOARD_TABS

        client = self._client(self.consultant)
        for key in list(DASHBOARD_TABS) + ["alarms"]:
            resp = client.get(reverse("dashboard_tab", args=[key]))
            self.assertEqual(resp.status_code, 200, key)
            data = json.loads(resp.content)
            self.assertIn("html", data, key)
            if key == "alarms":
                alarms = resp.context["alarms"]
                stale = sum(len(alarms[k]) for k in STALE_KEYS)
                self.assertEqual(data["count"], sum(len(v) for v in alarms.values()) - stale)
                self.assertEqual(data["stale"], stale)
            else:
                self.assertEqual(data["count"], len(resp.context["items"]), key)

    def test_index_badges_match_tab_counts(self):
        self._grant_all()
        client = self._client(self.consultant)
        index = client.get(reverse("dashboard"))
        for key, count in index.context["tab_counts"].items():
            data = json.loads(client.get(reverse("dashboard_tab", args=[key])).content)
            self.assertEqual(data["count"], count, key)
        alarms = json.loads(client.get(reverse("dashboard_tab", args=["alarms"])).content)
        self.assertEqual(alarms["count"], index.context["alarm_count"])

    def test_role_tabs_forbidden_without_role(self):
        client = self._client(self.consultant)
        for key in ["scoping", "signoff", "tqa", "pqa", "pending_delivery"]:
            self.assertEqual(
                client.get(reverse("dashboard_tab", args=[key])).status_code, 403, key
            )
        # Everyone's tabs stay open.
        for key in ["my_jobs", "my_phases", "in_flight", "alarms"]:
            self.assertEqual(
                client.get(reverse("dashboard_tab", args=[key])).status_code, 200, key
            )

    def test_unknown_tab_404(self):
        client = self._client(self.consultant)
        self.assertEqual(client.get(reverse("dashboard_tab", args=["nope"])).status_code, 404)

    def test_team_tabs_manager_only(self):
        client = self._client(self.consultant)
        self.assertEqual(client.get(reverse("dashboard_team_tab")).status_code, 403)
        self.assertEqual(client.get(reverse("dashboard_team_leave_tab")).status_code, 403)

    def test_alarms_render_inline_when_first(self):
        # Unit manager: the overdue phase is an alarm, so Alarms opens first
        # and is rendered inline (no second request for the visible tab).
        assign_perm("jobtracker.change_organisationalunit", self.consultant, self.unit)
        resp = self._client(self.consultant).get(reverse("dashboard"))
        self.assertTrue(resp.context["show_alarms_first"])
        self.assertContains(resp, 'data-tab-key="alarms"')
        self.assertContains(resp, 'data-loaded="true"')

    def test_index_queries_flat_as_rows_grow(self):
        """index only counts the tab lists (one COUNT each) - it no longer
        builds and renders them - so its cost doesn't grow with the rows."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._grant_all()
        client = self._client(self.consultant)
        url = reverse("dashboard")
        client.get(url)  # warm caches (constance, session)
        with CaptureQueriesContext(connection) as before:
            client.get(url)
        # 52 before the split for this fixture (all-roles user).
        self.assertLessEqual(len(before.captured_queries), 52)
        for i in range(10):
            Phase.objects.create(
                job=self.job, title="More {}".format(i),
                status=PhaseStatuses.IN_PROGRESS, project_lead=self.consultant,
            )
        with CaptureQueriesContext(connection) as after:
            client.get(url)
        self.assertEqual(len(after.captured_queries), len(before.captured_queries))
