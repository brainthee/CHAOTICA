"""Dashboard "My team's annual leave" tab — Manage button.

The tab is lazy-loaded, so its Manage buttons rely on core.js's delegated
``.js-load-modal-form`` handler. The button must also only appear where the
manage endpoint will actually open (it 403s for e.g. cancelled leave).
"""
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.enums import LeaveRequestTypes
from chaotica_utils.models import User
from chaotica_utils.models.leave import LeaveRequest


class TeamLeaveManageButtonTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(email="mgr@test.com", password="pw12345")
        self.report = User.objects.create_user(email="report@test.com", password="pw12345")
        self.report.manager = self.manager
        self.report.save()
        self.client = Client(HTTP_HOST="localhost")
        self.client.force_login(self.manager)

    def _leave(self, **kwargs):
        return LeaveRequest.objects.create(
            user=self.report,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            type_of_leave=LeaveRequestTypes.ANNUAL_LEAVE,
            **kwargs,
        )

    def _tab(self):
        resp = self.client.get(reverse("dashboard_team_leave_tab"))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_pending_leave_has_working_manage_button(self):
        leave = self._leave()
        url = reverse("manage_leave_auth_request", args=[leave.pk])
        self.assertIn(url, self._tab())
        # ...and that endpoint opens the modal for the manager.
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("html_form", resp.json())

    def test_cancelled_leave_has_no_manage_button(self):
        leave = self._leave(cancelled=True)
        url = reverse("manage_leave_auth_request", args=[leave.pk])
        self.assertNotIn(url, self._tab())
        self.assertEqual(self.client.get(url).status_code, 403)
