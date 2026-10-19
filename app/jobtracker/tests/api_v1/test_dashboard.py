"""Dashboard, alarms, stats, notifications (A4)."""

import json
from datetime import date, timedelta
from unittest import mock

from constance.test import override_config
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.enums import LeaveRequestTypes
from chaotica_utils.models import LeaveRequest, User
from jobtracker.enums import JobStatuses, PhaseStatuses
from jobtracker.models import Phase
from jobtracker.selectors.dashboard import DASHBOARD_TABS, DashboardScope
from notifications.enums import NotificationTypes
from notifications.models import Notification, NotificationSubscription

from .helpers import ApiV1TestCase, make_member


class DashboardTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.job = self.make_job(status=JobStatuses.IN_PROGRESS)
        self.member = make_member(
            User.objects.create_user(email="dash@example.com", password="pw"),
            self.job.unit,
        )
        self.phase = self.make_phase(
            self.job, project_lead=self.member, status=PhaseStatuses.IN_PROGRESS
        )

    def test_queues_match_the_page(self):
        body = self.as_user(self.member).get("/api/v1/me/dashboard/").json()
        scope = DashboardScope(self.member)
        expected = {
            key: getattr(scope, method)().count()
            for key, (method, audience, _t) in DASHBOARD_TABS.items()
            if audience is None or getattr(scope, audience)
        }
        self.assertEqual({q["key"]: q["count"] for q in body["queues"]}, expected)
        self.assertNotIn("scoping", expected)  # consultants don't scope
        my_phases = next(q for q in body["queues"] if q["key"] == "my_phases")
        self.assertEqual(my_phases["resource"], "phases")
        self.assertEqual(my_phases["count"], 1)

    def test_stats_and_team(self):
        body = self.as_user(self.member).get("/api/v1/me/dashboard/").json()
        self.assertEqual(body["stats"]["consultant"]["jobs_led"], 1)
        self.assertIn("utilisation_30d", body["stats"])
        self.assertIsNone(body["stats"]["utilisation_target"])
        self.assertEqual(body["team_unit"]["id"], self.job.unit.pk)
        self.assertIn(self.member.pk, {t["user"]["id"] for t in body["team"]})
        self.assertIn("overdue", body["alarm_counts"])

    def test_queue_filter_parity(self):
        client = self.as_user(self.member)
        resp = client.get("/api/v1/phases/?queue=my_phases")
        self.assert_same_ids(resp, Phase.objects.phases_for_user(self.member))
        self.assertEqual(client.get("/api/v1/phases/?queue=nope").status_code, 400)
        # Right key, wrong resource.
        self.assertEqual(client.get("/api/v1/jobs/?queue=my_phases").status_code, 400)
        # A queue this user doesn't get.
        resp = client.get("/api/v1/jobs/?queue=scoping")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "permission_denied")

    def test_alarms(self):
        Phase.objects.filter(pk=self.phase.pk).update(
            desired_delivery_date=date.today() - timedelta(days=5), number_of_reports=1
        )
        body = self.as_user(self.superuser).get("/api/v1/me/alarms/").json()
        ctx = DashboardScope(self.superuser).alarm_context()
        self.assertEqual(body["counts"]["overdue"], ctx["alarm_count"])
        overdue = {g["key"]: g for g in body["overdue"]}
        self.assertIn("delivery_overdue", overdue)
        item = overdue["delivery_overdue"]["items"][0]
        self.assertEqual(item["ref"]["id"], self.phase.pk)
        self.assertEqual(overdue["delivery_overdue"]["severity"], "critical")
        self.assertIn(self.member.pk, {p["id"] for p in item["people"]})

    @override_config(ENTROPY_METER_ENABLED=False)
    def test_entropy_off(self):
        self.assertEqual(
            self.as_user(self.member).get("/api/v1/entropy/").status_code, 404
        )

    @override_config(ENTROPY_METER_ENABLED=True)
    def test_entropy_on(self):
        resp = self.as_user(self.member).get("/api/v1/entropy/")
        self.assertEqual(resp.status_code, 200)

    def test_page_still_renders(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)


class PeopleTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.boss = User.objects.create_user(email="boss@example.com", password="pw")
        self.report = User.objects.create_user(email="rep@example.com", password="pw")
        self.report.manager = self.boss
        self.report.save()

    def test_manager_sees_reports(self):
        resp = self.as_user(self.boss).get("/api/v1/users/?manages=me")
        self.assert_same_ids(resp, User.objects.filter(pk=self.report.pk))

    def test_stats_gate(self):
        url = f"/api/v1/users/{self.report.pk}/stats/"
        self.assertEqual(self.as_user(self.report).get(url).status_code, 200)
        self.assertEqual(self.as_user(self.boss).get(url).status_code, 200)
        self.assertEqual(self.as_user(self.normal).get(url).status_code, 403)
        body = self.as_user(self.boss).get(url).json()
        self.assertEqual(len(body["tqa_feedback_12mo"]["months"]), 13)

    def test_team_leave(self):
        leave = LeaveRequest.objects.create(
            user=self.report,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            type_of_leave=LeaveRequestTypes.ANNUAL_LEAVE,
        )
        resp = self.as_user(self.boss).get(
            "/api/v1/leave-requests/?reports_of=me&status=pending"
        )
        rows = resp.json()["results"]
        self.assertEqual([r["id"] for r in rows], [leave.pk])
        self.assertTrue(rows[0]["can_authorise"])
        self.assertFalse(rows[0]["overlaps_work"])

    def test_feedback_window_follows_the_clock(self):
        """The 12-month default window used to be frozen at import."""
        later = timezone.now() + timedelta(days=400)
        with mock.patch("chaotica_utils.models.user.timezone.now", return_value=later):
            qs_filter = mock.MagicMock()
            with mock.patch.object(User, "get_reports") as get_reports:
                get_reports.return_value.filter = qs_filter
                self.report.get_average_techqa_feedback()
        kwargs = qs_filter.call_args.kwargs
        self.assertEqual(kwargs["actual_completed_date__lte"], later)


class NotificationTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.mine = [
            Notification.objects.create(user=self.normal, title=f"n{i}", message="m")
            for i in range(3)
        ]
        self.theirs = Notification.objects.create(
            user=self.superuser, title="x", message="m"
        )
        self.api = self.as_user(self.normal)

    def test_list_and_count(self):
        body = self.api.get("/api/v1/notifications/").json()
        self.assertEqual(body["count"], 3)
        resp = self.api.get("/api/v1/notifications/unread-count/").json()
        self.assertEqual(resp["unread_count"], 3)

    def test_mark_read_only_own(self):
        resp = self.api.post(
            "/api/v1/notifications/mark-read/",
            {"ids": [self.mine[0].pk, self.theirs.pk]},
            format="json",
        ).json()
        self.assertEqual(resp["updated"], 1)
        self.assertEqual(resp["unread_count"], 2)
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.read)

    def test_mark_all_read(self):
        resp = self.api.post("/api/v1/notifications/mark-all-read/").json()
        self.assertEqual(resp["updated"], 3)
        self.assertEqual(
            self.api.get("/api/v1/notifications/?unread_only=true").json()["count"], 0
        )

    def test_widget_uses_v1(self):
        self.client.force_login(self.normal)
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn(reverse("api_v1:notifications"), page)
        self.assertIn("/ws/me/", page)
        self.assertIn("escapeHtml(n.title)", page)

    def test_legacy_subscription_update_accepts_id(self):
        sub = NotificationSubscription.objects.create(
            user=self.normal, notification_type=NotificationTypes.SYSTEM
        )
        self.client.force_login(self.normal)
        resp = self.client.post(
            reverse("update_subscription_settings") + f"?subscription_id={sub.pk}",
            json.dumps({"email_enabled": False}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        sub.refresh_from_db()
        self.assertFalse(sub.email_enabled)
