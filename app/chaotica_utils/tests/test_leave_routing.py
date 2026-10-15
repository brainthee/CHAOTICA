"""Leave reaches the right approver; managers stay current (T-07)."""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestHttpClient, TestCase
from django.urls import reverse
from django.utils import timezone
from guardian.shortcuts import assign_perm

from chaotica_utils.enums import LeaveRequestTypes
from chaotica_utils.forms.common import EditProfileForm
from chaotica_utils.models import User
from chaotica_utils.models.audit import AuditEvent
from chaotica_utils.models.leave import LeaveRequest
from jobtracker.models import (
    OrganisationalUnit,
    OrganisationalUnitMember,
    OrganisationalUnitRole,
)
from notifications.criteria_registry import user_manager
from notifications.enums import NotificationTypes
from notifications.models import (
    DynamicRuleCriteria,
    NotificationSubscription,
    OrgUnitRoleCriteria,
    SubscriptionRule,
)


class _Base(TestCase):
    def setUp(self):
        # First user is auto-promoted to superuser; keep it out of the way.
        User.objects.create_user(email="root@route.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="Route Unit")
        self.person = User.objects.create_user(email="person@route.com", password="pw")
        self.boss = User.objects.create_user(email="boss@route.com", password="pw")
        self.new_boss = User.objects.create_user(email="newboss@route.com", password="pw")
        self.approver = User.objects.create_user(email="sd@route.com", password="pw")
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.person)
        OrganisationalUnitMember.objects.create(unit=self.unit, member=self.approver)
        # After the membership saves (they resync unit perms from roles).
        assign_perm("jobtracker.can_approve_leave_requests", self.approver, self.unit)

    def _leave(self, **kwargs):
        defaults = dict(
            user=User.objects.get(pk=self.person.pk),
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            type_of_leave=LeaveRequestTypes.ANNUAL_LEAVE,
        )
        defaults.update(kwargs)
        return LeaveRequest.objects.create(**defaults)

    def _set(self, user, **fields):
        user = User.objects.get(pk=user.pk)
        for k, v in fields.items():
            setattr(user, k, v)
        user.save()
        return user


class ApproverRoutingTests(_Base):
    def test_acting_manager_only_is_notified(self):
        self._set(self.person, acting_manager=self.boss)
        leave = self._leave()
        self.assertEqual(list(user_manager(leave)), [self.boss])
        self.assertEqual(list(leave.get_approvers()), [self.boss])

    def test_manager_and_acting_both_returned_active_only(self):
        self._set(self.person, manager=self.boss, acting_manager=self.new_boss)
        self._set(self.new_boss, is_active=False)
        leave = self._leave()
        self.assertEqual(list(user_manager(leave)), [self.boss])

    def test_inactive_manager_falls_back_to_unit_approvers(self):
        self._set(self.person, manager=self.boss)
        self._set(self.boss, is_active=False)
        leave = LeaveRequest.objects.get(pk=self._leave().pk)
        self.assertEqual(list(leave.get_approvers()), [self.approver])
        self.assertEqual(list(user_manager(leave)), [self.approver])
        self.assertTrue(leave.can_user_auth(self.approver))
        self.assertFalse(leave.can_user_auth(leave.user))

    def test_no_manager_routes_to_unit_approvers_not_self(self):
        leave = self._leave()
        self.assertEqual(list(leave.get_approvers()), [self.approver])
        self.assertFalse(leave.can_user_auth(self.person))

    def test_former_unit_role_holders_not_notified(self):
        role = OrganisationalUnitRole.objects.create(name="Leave Approver Test")
        criteria = OrgUnitRoleCriteria(unit_role=role)
        former = User.objects.create_user(email="former@route.com", password="pw")
        ms = OrganisationalUnitMember.objects.create(unit=self.unit, member=former)
        ms.roles.add(role)
        current = OrganisationalUnitMember.objects.get(unit=self.unit, member=self.approver)
        current.roles.add(role)
        leave = self._leave()
        self.assertEqual(
            set(criteria.get_matching_users(leave)), {former, self.approver}
        )
        ms.left_date = timezone.now()
        ms.save()
        self.assertEqual(set(criteria.get_matching_users(leave)), {self.approver})


class ReassignOnManagerChangeTests(_Base):
    def setUp(self):
        super().setUp()
        self.rule = SubscriptionRule.objects.create(
            name="Leave Submitted", notification_type=NotificationTypes.LEAVE_SUBMITTED
        )
        DynamicRuleCriteria.objects.create(
            rule=self.rule, criteria_name="user_manager", parameters={}
        )

    def _subscribers(self, leave):
        return set(
            NotificationSubscription.objects.filter(
                entity_type="LeaveRequest",
                entity_id=leave.pk,
                notification_type=NotificationTypes.LEAVE_SUBMITTED,
            ).values_list("user__email", flat=True)
        )

    def test_pending_request_moves_to_new_manager(self):
        self._set(self.person, manager=self.boss)
        leave = self._leave()
        self.assertEqual(self._subscribers(leave), {self.boss.email})
        self._set(self.person, manager=self.new_boss)
        self.assertEqual(self._subscribers(leave), {self.new_boss.email})

    def test_manager_deactivated_moves_request_to_unit_approvers(self):
        self._set(self.person, manager=self.boss)
        leave = self._leave()
        self._set(self.boss, is_active=False)
        self.assertEqual(self._subscribers(leave), {self.approver.email})

    def test_past_request_left_alone(self):
        self._set(self.person, manager=self.boss)
        leave = self._leave(
            start_date=timezone.now() - timedelta(days=9),
            end_date=timezone.now() - timedelta(days=8),
        )
        self._set(self.person, manager=self.new_boss)
        self.assertEqual(self._subscribers(leave), {self.boss.email})


class SelfEditLockTests(_Base):
    class _Req:
        def __init__(self, user, method="POST"):
            self.user = user
            self.method = method

    def test_self_service_cannot_change_manager_or_allowance(self):
        req = self._Req(User.objects.get(pk=self.person.pk))
        form = EditProfileForm(instance=self.person, current_request=req)
        for f in ("manager", "acting_manager", "contracted_leave", "carry_over_leave"):
            self.assertTrue(form.fields[f].disabled, f)

    def test_manager_can_change_them(self):
        self._set(self.person, manager=self.boss)
        person = User.objects.get(pk=self.person.pk)
        req = self._Req(User.objects.get(pk=self.boss.pk))
        form = EditProfileForm(instance=person, current_request=req)
        self.assertFalse(form.fields["manager"].disabled)

    def test_acting_manager_choices_are_active_only(self):
        self._set(self.new_boss, is_active=False)
        req = self._Req(User.objects.get(pk=self.person.pk))
        form = EditProfileForm(instance=self.person, current_request=req)
        self.assertNotIn(self.new_boss, form.fields["acting_manager"].queryset)


class ManagerImportTests(_Base):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(email="admin@route.com", password="pw")
        assign_perm("chaotica_utils.manage_user", self.admin)
        self.http = TestHttpClient(HTTP_HOST="localhost")
        self.http.force_login(self.admin)
        self.url = reverse("user_import_managers")

    def _upload(self, body):
        f = SimpleUploadedFile("m.csv", body.encode(), "text/csv")
        return self.http.post(self.url, {"csv_file": f})

    def test_requires_manage_user(self):
        self.http.force_login(self.person)
        self.assertEqual(self.http.get(self.url).status_code, 403)
        self.assertEqual(
            self.http.get(reverse("user_import_managers_template")).status_code, 403
        )

    def test_dry_run_then_apply(self):
        self._set(self.boss, manager=self.new_boss)
        self._set(self.approver, manager=self.boss)
        resp = self._upload(
            "email,manager_email,acting_manager_email\n"
            "person@route.com,Boss@route.com,\n"
            "sd@route.com,boss@route.com,\n"
        )
        self.assertEqual(resp.status_code, 200)
        plan = resp.context["plan"]
        self.assertEqual([e["status"] for e in plan], ["change", "same"])
        # Dry run changed nothing.
        self.assertIsNone(User.objects.get(pk=self.person.pk).manager)

        resp = self.http.post(self.url, {"action": "apply"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.get(pk=self.person.pk).manager, self.boss)
        self.assertTrue(
            AuditEvent.objects.filter(
                target_id=str(self.person.pk), message__contains="manager import"
            ).exists()
        )
        # Session cleared: a second apply has nothing to do.
        self.http.post(self.url, {"action": "apply"})
        self.assertEqual(
            AuditEvent.objects.filter(message__contains="manager import").count(), 1
        )

    def test_failure_reasons(self):
        self._set(self.boss, manager=self.person)
        self._set(self.new_boss, is_active=False)
        resp = self._upload(
            "email,manager_email,acting_manager_email\n"
            "ghost@route.com,boss@route.com,\n"
            "person@route.com,newboss@route.com,\n"
            "person@route.com,nobody@route.com,\n"
            "sd@route.com,sd@route.com,\n"
            "person@route.com,boss@route.com,\n"
            ",boss@route.com,\n"
        )
        reasons = [e.get("reason") for e in resp.context["plan"]]
        self.assertEqual(
            reasons,
            [
                "Unknown person",
                "Manager newboss@route.com is deactivated",
                "Duplicate row for this person",
                "Can't be their own manager",
                "Duplicate row for this person",
                "No email",
            ],
        )

    def test_loop_and_clear(self):
        self._set(self.boss, manager=self.person)
        resp = self._upload(
            "email,manager_email,acting_manager_email\nperson@route.com,boss@route.com,\n"
        )
        self.assertEqual(
            resp.context["plan"][0]["reason"], "Would create a management loop"
        )
        self._set(self.person, acting_manager=self.approver)
        resp = self._upload(
            "email,manager_email,acting_manager_email\nperson@route.com,,-\n"
        )
        self.assertEqual(resp.context["plan"][0]["status"], "change")
        self.http.post(self.url, {"action": "apply"})
        self.assertIsNone(User.objects.get(pk=self.person.pk).acting_manager)

    def test_missing_email_column_rejected(self):
        resp = self._upload("name,manager_email\nx,y\n")
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
