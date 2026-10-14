"""Leave approval, user calendar, notification-follow and self-manager scoping."""

import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from guardian.shortcuts import assign_perm

from chaotica_utils.enums import LeaveRequestTypes
from chaotica_utils.forms.common import EditProfileForm
from chaotica_utils.models import User
from chaotica_utils.models.leave import LeaveRequest
from jobtracker.models import Client, Job, OrganisationalUnit, OrganisationalUnitMember


class _Base(TestCase):
    def setUp(self):
        # First user is auto-promoted to superuser; keep it out of the way.
        User.objects.create_user(email="bootstrap@test.com", password="pw12345")
        self.unit = OrganisationalUnit.objects.create(name="Unit A")
        self.requester = User.objects.create_user(email="req@test.com", password="pw12345")
        self.approver = User.objects.create_user(email="appr@test.com", password="pw12345")
        self.outsider = User.objects.create_user(email="out@test.com", password="pw12345")

    def _member(self, user, unit=None, left=False):
        membership = OrganisationalUnitMember.objects.create(unit=unit or self.unit, member=user)
        if left:
            membership.left_date = timezone.now()
            membership.save()
        return membership


class LeaveApprovalScopeTests(_Base):
    def _leave(self, user):
        return LeaveRequest.objects.create(
            user=user,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            type_of_leave=LeaveRequestTypes.ANNUAL_LEAVE,
        )

    def test_unit_approver_can_approve_current_member(self):
        self._member(self.requester)
        assign_perm("jobtracker.can_approve_leave_requests", self.approver, self.unit)
        self.assertTrue(self._leave(self.requester).can_user_auth(self.approver))

    def test_unit_approver_cannot_approve_former_member(self):
        self._member(self.requester, left=True)
        assign_perm("jobtracker.can_approve_leave_requests", self.approver, self.unit)
        self.assertFalse(self._leave(self.requester).can_user_auth(self.approver))

    def test_unit_approver_cannot_approve_own_leave(self):
        self.approver.manager = self.outsider
        self.approver.save()
        self._member(self.approver)
        assign_perm("jobtracker.can_approve_leave_requests", self.approver, self.unit)
        self.assertFalse(self._leave(self.approver).can_user_auth(self.approver))


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class UserCalendarScopeTests(_Base):
    def _get(self, viewer, target):
        self.client.force_login(viewer)
        return self.client.get(
            reverse("user_schedule_timeslots", kwargs={"email": target.email}),
            HTTP_HOST="testserver",
        )

    def test_unrelated_user_cannot_read_calendar(self):
        self.assertEqual(self._get(self.outsider, self.requester).status_code, 403)

    def test_manager_can_read_calendar(self):
        self.requester.manager = self.approver
        self.requester.save()
        self.assertEqual(self._get(self.approver, self.requester).status_code, 200)

    def test_unit_schedule_viewer_can_read_calendar(self):
        self._member(self.requester)
        assign_perm("jobtracker.view_users_schedule", self.approver, self.unit)
        self.assertEqual(self._get(self.approver, self.requester).status_code, 200)

    def test_self_can_read_calendar(self):
        self.assertEqual(self._get(self.requester, self.requester).status_code, 200)


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class FollowEntityScopeTests(_Base):
    def setUp(self):
        super().setUp()
        self.job = Job.objects.create(
            unit=self.unit, client=Client.objects.create(name="C"), title="J",
            created_by=self.approver, account_manager=self.approver,
        )

    def _follow(self, user):
        self.client.force_login(user)
        return self.client.post(
            reverse("follow_entity"),
            json.dumps({"entity_type": "Job", "entity_id": self.job.id}),
            content_type="application/json",
            HTTP_HOST="testserver",
        )

    def test_cannot_follow_job_you_cannot_see(self):
        self.assertEqual(self._follow(self.outsider).status_code, 403)

    def test_can_follow_visible_job(self):
        assign_perm("jobtracker.can_view_jobs", self.requester, self.unit)
        self.assertEqual(self._follow(self.requester).status_code, 200)


class SelfManagerTests(_Base):
    def test_cannot_set_self_as_manager(self):
        class _Req:
            user = None

        req = _Req()
        req.user = self.requester
        form = EditProfileForm(
            data={"manager": self.requester.pk, "acting_manager": self.requester.pk},
            instance=self.requester,
            current_request=req,
        )
        form.is_valid()
        self.assertIn("manager", form.errors)
        self.assertIn("acting_manager", form.errors)
