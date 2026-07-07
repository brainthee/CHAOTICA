"""Dashboard scoping tests.

Regression cover for the leak where consultants saw jobs/phases they had no part
in. The personal operational tabs (In Flight / Scheduled This Week / Upcoming
Reports) must only show phases the user is involved in unless they are a
people-manager or hold a job-oversight role; the Alarms tab must only go unit-wide
for job-oversight roles (QA/scope/deliver/signoff), never for a plain
people-manager.
"""

from datetime import timedelta

from django.test import TestCase, Client, override_settings
from django.utils import timezone
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User
from jobtracker.models import (
    Client as JobClient,
    Job,
    OrganisationalUnit,
    Phase,
)
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
        # but is not scheduled/lead/author on the phase, and manages nobody.
        self.consultant = User.objects.create_user(
            email="consultant@test.com", password="pw12345"
        )
        assign_perm("jobtracker.can_view_jobs", self.consultant, self.unit)

    def _dashboard_context(self, user):
        # Re-fetch to clear guardian's per-instance permission cache.
        user = User.objects.get(pk=user.pk)
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)
        resp = client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)
        return resp.context

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
