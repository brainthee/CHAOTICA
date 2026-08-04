"""Tests for the day-based ``Project.get_stats`` and the member-scoped
``Team.get_stats`` aggregates that feed the new Stats tabs.

Business-hour totals depend on the working calendar, so these tests assert the
*structure* and *relationships* of the aggregates (confirmed/tentative split,
past vs future, distinct de-duplication) rather than brittle absolute day
counts. The custom SessionMiddleware rejects requests without HTTP_HOST, so the
view smoke test constructs its client with ``HTTP_HOST='localhost'``.
"""

import json
from datetime import timedelta

from django.test import TestCase, Client as TestHttpClient
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import User
from jobtracker.models import (
    Client,
    Job,
    Phase,
    Project,
    OrganisationalUnit,
    TimeSlot,
    TimeSlotType,
    Team,
    TeamMember,
)
from jobtracker.models.service import Service
from jobtracker.enums import (
    DefaultTimeSlotTypes,
    PhaseStatuses,
    ProjectState,
    TimeSlotDeliveryRole,
)


def _weekday_slot_times(base):
    """Return (start, end) for a single ~business-day slot on a Monday.

    Anchors to the Monday of ``base``'s week so the slot always lands on a
    working weekday (business-hour maths returns 0 on weekends).
    """
    monday = (base - timedelta(days=base.weekday())).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    return monday, monday.replace(hour=17, minute=30)


class ProjectGetStatsTests(TestCase):
    def setUp(self):
        # First user is force-promoted to superuser by User.save(); keep it
        # aside so the actors below are plain accounts.
        self.root = User.objects.create_user(email="root@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="Unit")
        self.client_obj = Client.objects.create(name="Acme")
        self.u1 = User.objects.create_user(email="u1@test.com", password="pw")
        self.u2 = User.objects.create_user(email="u2@test.com", password="pw")
        # Project slots use a project/working slot type (not the phase-DELIVERY
        # type, which drives phase transitions and expects a phase).
        self.slot_type = TimeSlotType.objects.create(
            name="Project Work", is_working=True, is_delivery=False
        )

        now = timezone.now()
        self.past_start, self.past_end = _weekday_slot_times(now - timedelta(days=21))
        self.future_start, self.future_end = _weekday_slot_times(now + timedelta(days=21))

    def _project(self, state=ProjectState.CONFIRMED, deliverable=True):
        return Project.objects.create(
            title="RM project",
            unit=self.unit,
            client=self.client_obj,
            created_by=self.root,
            state=state,
            deliverable=deliverable,
        )

    def _slot(self, project, user, start, end, role=TimeSlotDeliveryRole.DELIVERY):
        return TimeSlot.objects.create(
            user=user,
            slot_type=self.slot_type,
            project=project,
            start=start,
            end=end,
            deliveryRole=role,
        )

    def test_empty_project_is_all_zero_and_safe(self):
        stats = self._project().get_stats()
        self.assertEqual(stats["summary"]["total_days"], 0)
        self.assertEqual(stats["summary"]["team_size"], 0)
        self.assertEqual(stats["users_data"], [])
        self.assertEqual(stats["roles_data"], [])
        self.assertEqual(stats["monthly_data"], [])

    def test_get_hours_in_day_falls_back_without_client(self):
        p = Project.objects.create(title="No client", created_by=self.root)
        # No client set -> default divisor, and no crash.
        self.assertGreater(p.get_hours_in_day(), 0)
        self.assertEqual(p.get_stats()["summary"]["total_days"], 0)

    def test_summary_used_scheduled_and_team_size(self):
        p = self._project()
        self._slot(p, self.u1, self.past_start, self.past_end)
        self._slot(p, self.u1, self.future_start, self.future_end)
        self._slot(p, self.u2, self.future_start, self.future_end)
        stats = p.get_stats()
        s = stats["summary"]

        self.assertEqual(s["team_size"], 2)
        self.assertGreater(s["used_days"], 0)
        self.assertGreater(s["scheduled_days"], 0)
        # No slot straddles "now", so used + scheduled should reconstruct total.
        self.assertAlmostEqual(s["used_days"] + s["scheduled_days"], s["total_days"], delta=0.2)

    def test_confirmed_project_counts_all_days_as_confirmed(self):
        p = self._project(state=ProjectState.CONFIRMED, deliverable=True)
        self._slot(p, self.u1, self.past_start, self.past_end)
        s = p.get_stats()["summary"]
        self.assertGreater(s["confirmed_days"], 0)
        self.assertEqual(s["confirmed_days"], s["total_days"])
        self.assertEqual(s["tentative_days"], 0)

    def test_tentative_project_counts_all_days_as_tentative(self):
        p = self._project(state=ProjectState.TENTATIVE, deliverable=True)
        self._slot(p, self.u1, self.past_start, self.past_end)
        s = p.get_stats()["summary"]
        self.assertEqual(s["confirmed_days"], 0)
        self.assertEqual(s["tentative_days"], s["total_days"])

    def test_roles_and_users_breakdown(self):
        p = self._project()
        self._slot(p, self.u1, self.past_start, self.past_end, TimeSlotDeliveryRole.DELIVERY)
        self._slot(p, self.u2, self.future_start, self.future_end, TimeSlotDeliveryRole.QA)
        # A role-0 (NA) slot must be excluded from the per-role breakdown.
        self._slot(p, self.u1, self.future_start, self.future_end, TimeSlotDeliveryRole.NA)
        stats = p.get_stats()

        role_names = {r["role_name"] for r in stats["roles_data"]}
        self.assertIn("Delivery", role_names)
        self.assertIn("QA", role_names)
        self.assertNotIn("None", role_names)

        self.assertEqual(len(stats["users_data"]), 2)
        totals = [u["total_days"] for u in stats["users_data"]]
        self.assertEqual(totals, sorted(totals, reverse=True))
        # Each member carries their delivery role labels + a share pct.
        for entry in stats["users_data"]:
            self.assertIn("roles", entry)
            self.assertIn("pct", entry)

    def test_monthly_burndown_cumulative_is_monotonic(self):
        p = self._project()
        # Two past slots in different months -> two burn-down buckets.
        older_start, older_end = _weekday_slot_times(timezone.now() - timedelta(days=55))
        self._slot(p, self.u1, older_start, older_end)
        self._slot(p, self.u1, self.past_start, self.past_end)
        monthly = p.get_stats()["monthly_data"]
        self.assertGreaterEqual(len(monthly), 1)
        cumulative = [m["cumulative"] for m in monthly]
        self.assertEqual(cumulative, sorted(cumulative))

    def test_monthly_burndown_fills_gap_months(self):
        p = self._project()
        # Two slots ~4 months apart -> the interior months with no slots must
        # still appear (as 0-day buckets) so the burn-down doesn't skip them.
        old_start, old_end = _weekday_slot_times(timezone.now() - timedelta(days=130))
        self._slot(p, self.u1, old_start, old_end)
        self._slot(p, self.u1, self.past_start, self.past_end)
        monthly = p.get_stats()["monthly_data"]
        keys = [m["month"] for m in monthly]
        # Months are contiguous (no gaps) and sorted.
        self.assertEqual(keys, sorted(keys))
        self.assertGreaterEqual(len(keys), 3)
        self.assertTrue(any(m["days"] == 0 for m in monthly))
        # A flat stretch: cumulative never decreases across the empty months.
        cumulative = [m["cumulative"] for m in monthly]
        self.assertEqual(cumulative, sorted(cumulative))

    def test_stats_partial_view_returns_both_render_targets(self):
        p = self._project()
        self._slot(p, self.u1, self.past_start, self.past_end)
        http = TestHttpClient(HTTP_HOST="localhost")
        http.force_login(self.root)  # root is superuser -> passes view_project
        resp = http.get(reverse("project_stats_partial", kwargs={"slug": p.slug}))
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertIn("html", payload)
        self.assertIn("members_html", payload)
        self.assertIn("u1@test.com", payload["members_html"])


class TeamGetStatsTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_user(email="root@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="Unit")
        self.client_obj = Client.objects.create(name="Acme")
        self.m1 = User.objects.create_user(email="m1@test.com", password="pw")
        self.m2 = User.objects.create_user(email="m2@test.com", password="pw")
        self.slot_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)

        self.team = Team.objects.create(name="Red Team")
        joined = timezone.now().date() - timedelta(days=30)
        TeamMember.objects.create(team=self.team, user=self.m1, joined_at=joined)
        TeamMember.objects.create(team=self.team, user=self.m2, joined_at=joined)

        self.service = Service.objects.create(name="Web App Test")
        self.job = Job.objects.create(
            unit=self.unit,
            client=self.client_obj,
            title="Job",
            created_by=self.root,
            account_manager=self.root,
        )
        self.phase = Phase.objects.create(job=self.job, title="Phase 1")
        self.phase.service = self.service
        self.phase.status = PhaseStatuses.DELIVERED
        self.phase.actual_delivery_date = timezone.now() - timedelta(days=5)
        self.phase.save()

        # ONE phase, MANY timeslots across BOTH members -> the distinct=True
        # counts must still report the phase/job exactly once.
        start, end = _weekday_slot_times(timezone.now() - timedelta(days=14))
        for user in (self.m1, self.m1, self.m2):
            TimeSlot.objects.create(
                user=user,
                slot_type=self.slot_type,
                phase=self.phase,
                start=start,
                end=end,
                deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            )

    def test_empty_team_is_safe(self):
        empty = Team.objects.create(name="Empty")
        stats = empty.get_stats()
        self.assertEqual(stats["summary"]["active_members"], 0)
        self.assertEqual(stats["service_breakdown"], [])
        self.assertEqual(stats["job_status_breakdown"], [])
        self.assertEqual(stats["member_utilisation"], [])

    def test_summary_counts_members_and_active_jobs(self):
        s = self.team.get_stats()["summary"]
        self.assertEqual(s["active_members"], 2)
        self.assertEqual(s["active_jobs"], 1)
        self.assertEqual(s["phases_delivered"], 1)

    def test_service_breakdown_deduplicated_by_distinct(self):
        breakdown = self.team.get_stats()["service_breakdown"]
        self.assertEqual(len(breakdown), 1)
        self.assertEqual(breakdown[0]["name"], "Web App Test")
        # 3 slots across 2 members on 1 phase -> still counts the phase once.
        self.assertEqual(breakdown[0]["participation_count"], 1)

    def test_job_pipeline_deduplicated_by_distinct(self):
        pipeline = self.team.get_stats()["job_status_breakdown"]
        self.assertEqual(len(pipeline), 1)
        self.assertEqual(pipeline[0]["count"], 1)

    def test_delivery_throughput_counts_phase_once(self):
        throughput = self.team.get_stats()["delivery_throughput"]
        self.assertEqual(sum(throughput["counts"]), 1)

    def test_member_utilisation_has_row_per_member(self):
        rows = self.team.get_stats()["member_utilisation"]
        self.assertEqual(len(rows), 2)
        user_ids = {r["user_id"] for r in rows}
        self.assertEqual(user_ids, {self.m1.pk, self.m2.pk})
        for r in rows:
            self.assertIn("confirmed_pct", r)

    def test_stats_json_serialises(self):
        # The partial serialises stats via json.dumps(default=str); the member
        # rows carry model instances, so confirm nothing blows up.
        stats = self.team.get_stats()
        self.assertIsInstance(json.dumps(stats, default=str), str)
