from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from chaotica_utils.models import User
from chaotica_utils.models.leave import LeaveRequest
from chaotica_utils.enums import LeaveRequestTypes


class LeaveRequestTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="leaveuser@test.com", password="testpass123"
        )
        self.manager = User.objects.create_user(
            email="leavemanager@test.com", password="testpass123"
        )
        self.other = User.objects.create_user(
            email="leaveother@test.com", password="testpass123"
        )

    def _create_leave(self, **kwargs):
        defaults = {
            "user": self.user,
            "start_date": timezone.now() + timedelta(days=7),
            "end_date": timezone.now() + timedelta(days=8),
            "type_of_leave": LeaveRequestTypes.ANNUAL_LEAVE,
        }
        defaults.update(kwargs)
        return LeaveRequest.objects.create(**defaults)


class CanCancelTests(LeaveRequestTestBase):
    def test_can_cancel_future_leave(self):
        leave = self._create_leave()
        self.assertTrue(leave.can_cancel())

    def test_can_cancel_past_leave(self):
        leave = self._create_leave(
            start_date=timezone.now() - timedelta(days=2),
            end_date=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(leave.can_cancel())

    def test_can_cancel_already_cancelled(self):
        leave = self._create_leave(cancelled=True)
        self.assertFalse(leave.can_cancel())


class CanApproveByTests(LeaveRequestTestBase):
    def test_can_approve_by_manager(self):
        self.user.manager = self.manager
        self.user.save()
        leave = self._create_leave()
        approvers = leave.can_approve_by()
        self.assertIn(self.manager, approvers)

    def test_can_approve_by_both_managers(self):
        self.user.manager = self.manager
        self.user.acting_manager = self.other
        self.user.save()
        leave = self._create_leave()
        approvers = leave.can_approve_by()
        self.assertIn(self.manager, approvers)
        self.assertIn(self.other, approvers)

    def test_can_approve_by_self_when_no_managers(self):
        leave = self._create_leave()
        approvers = leave.can_approve_by()
        self.assertIn(self.user, approvers)


class CanUserAuthTests(LeaveRequestTestBase):
    def test_can_user_auth_manager(self):
        self.user.manager = self.manager
        self.user.save()
        leave = self._create_leave()
        self.assertTrue(leave.can_user_auth(self.manager))

    def test_can_user_auth_acting_manager(self):
        self.user.acting_manager = self.manager
        self.user.save()
        leave = self._create_leave()
        self.assertTrue(leave.can_user_auth(self.manager))

    def test_can_user_auth_self_no_managers(self):
        leave = self._create_leave()
        self.assertTrue(leave.can_user_auth(self.user))

    def test_can_user_auth_unrelated(self):
        self.user.manager = self.manager
        self.user.save()
        leave = self._create_leave()
        self.assertFalse(leave.can_user_auth(self.other))

    def test_can_user_auth_cancelled(self):
        self.user.manager = self.manager
        self.user.save()
        leave = self._create_leave(cancelled=True)
        self.assertFalse(leave.can_user_auth(self.manager))


class RequestedLateTests(LeaveRequestTestBase):
    def test_requested_late(self):
        # Start date within the notice period (only 5 days out, less than 14)
        leave = self._create_leave(
            start_date=timezone.now() + timedelta(days=5),
            end_date=timezone.now() + timedelta(days=6),
        )
        self.assertTrue(leave.requested_late())

    def test_requested_not_late(self):
        # Start date well beyond the notice period
        leave = self._create_leave(
            start_date=timezone.now() + timedelta(days=30),
            end_date=timezone.now() + timedelta(days=31),
        )
        self.assertFalse(leave.requested_late())


class AuthoriseTests(LeaveRequestTestBase):
    @patch("chaotica_utils.models.leave.send_notifications")
    def test_authorise_sets_fields(self, mock_notify):
        self.user.manager = self.manager
        self.user.save()
        leave = self._create_leave()
        leave.authorise(self.manager)
        leave.refresh_from_db()
        self.assertTrue(leave.authorised)
        self.assertEqual(leave.authorised_by, self.manager)
        self.assertIsNotNone(leave.authorised_on)
        self.assertIsNotNone(leave.timeslot)

    @patch("chaotica_utils.models.leave.send_notifications")
    def test_authorise_cancelled_returns_false(self, mock_notify):
        leave = self._create_leave(cancelled=True)
        result = leave.authorise(self.manager)
        self.assertFalse(result)

    @patch("chaotica_utils.models.leave.send_notifications")
    def test_authorise_already_authorised_no_op(self, mock_notify):
        self.user.manager = self.manager
        self.user.save()
        leave = self._create_leave()
        leave.authorise(self.manager)
        leave.refresh_from_db()
        timeslot_pk = leave.timeslot.pk
        # Authorise again — should be a no-op
        leave.authorise(self.manager)
        leave.refresh_from_db()
        self.assertEqual(leave.timeslot.pk, timeslot_pk)


class DeclineTests(LeaveRequestTestBase):
    @patch("chaotica_utils.models.leave.send_notifications")
    def test_decline_sets_fields(self, mock_notify):
        self.user.manager = self.manager
        self.user.save()
        leave = self._create_leave()
        leave.decline(self.manager)
        leave.refresh_from_db()
        self.assertTrue(leave.declined)
        self.assertEqual(leave.declined_by, self.manager)


class CancelTests(LeaveRequestTestBase):
    @patch("chaotica_utils.models.leave.send_notifications")
    def test_cancel_sets_fields(self, mock_notify):
        leave = self._create_leave()
        leave.cancel()
        leave.refresh_from_db()
        self.assertTrue(leave.cancelled)
        self.assertFalse(leave.authorised)

    @patch("chaotica_utils.models.leave.send_notifications")
    def test_cancel_already_cancelled_no_op(self, mock_notify):
        leave = self._create_leave(cancelled=True)
        original_cancelled_on = leave.cancelled_on
        leave.cancel()
        leave.refresh_from_db()
        self.assertEqual(leave.cancelled_on, original_cancelled_on)
