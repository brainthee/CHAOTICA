"""Reactivated people return to their units (T-04).

Deactivation closes every open unit/team membership; reactivation reopens the
ones it closed (roles and permissions intact). Add member, pre-load, CSV import
and ensure_lead_memberships reopen a left membership rather than refusing it,
and the team table's former-members list offers a manage_members-gated Rejoin.
"""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from guardian.shortcuts import assign_perm, get_user_perms

from chaotica_utils.models import User
from jobtracker.models import OrganisationalUnitMember, Team, TeamMember
from notifications.criteria_registry import unit_members

from .test_preload_members import PreloadMemberBase


class ReactivationReopensMembershipsTests(PreloadMemberBase):
    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(email="back@test.com", password="pw")
        self.membership = OrganisationalUnitMember.objects.create(
            unit=self.unit, member=self.person
        )
        self.membership.roles.add(self.consultant_role)
        self.unit.sync_permissions(users=[self.person.pk])
        self.team = Team.objects.create(name="Blue Team")
        self.team_row = TeamMember.objects.create(team=self.team, user=self.person)

    def test_deactivate_then_reactivate_restores_membership_roles_perms(self):
        perms_before = set(get_user_perms(self.person, self.unit))
        self.assertTrue(perms_before)

        self.person.set_active_status(False)
        self.membership.refresh_from_db()
        self.team_row.refresh_from_db()
        self.assertIsNotNone(self.membership.left_date)
        self.assertIsNotNone(self.team_row.left_at)

        self.person.set_active_status(True)
        self.membership.refresh_from_db()
        self.team_row.refresh_from_db()
        self.assertIsNone(self.membership.left_date)
        self.assertIsNone(self.team_row.left_at)
        self.assertEqual(list(self.membership.roles.all()), [self.consultant_role])
        self.assertEqual(set(get_user_perms(self.person, self.unit)), perms_before)
        self.assertIn(self.person, self.unit.get_activeMembers())

    def test_membership_left_earlier_stays_closed(self):
        from jobtracker.models import OrganisationalUnit

        other_unit = OrganisationalUnit.objects.create(name="Old Unit")
        old = OrganisationalUnitMember.objects.create(
            unit=other_unit, member=self.person
        )
        old.left_date = timezone.now() - timedelta(days=90)
        old.save()

        self.person.set_active_status(False)
        self.person.set_active_status(True)
        old.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertIsNotNone(old.left_date)
        self.assertIsNone(self.membership.left_date)

    def test_reactivation_without_open_memberships_reopens_nothing(self):
        # They'd left the unit for other reasons before being deactivated.
        self.membership.left_date = timezone.now() - timedelta(days=30)
        self.membership.save()
        self.person.set_active_status(False)
        self.person.set_active_status(True)
        self.membership.refresh_from_db()
        self.assertIsNotNone(self.membership.left_date)

    def test_audit_wording(self):
        from chaotica_utils.models.audit import AuditEvent

        self.person.set_active_status(False)
        self.person.set_active_status(True)
        messages = list(
            AuditEvent.objects.filter(target_id=str(self.person.pk))
            .order_by("timestamp")
            .values_list("message", flat=True)
        )
        self.assertIn("Account deactivated", messages)
        self.assertIn("Account reactivated", messages)


class ReopenInsteadOfRefuseTests(PreloadMemberBase):
    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(email="left@test.com", password="pw")
        self.membership = OrganisationalUnitMember.objects.create(
            unit=self.unit, member=self.person
        )
        self.membership.roles.add(self.consultant_role)
        self.membership.left_date = timezone.now() - timedelta(days=10)
        self.membership.save()

    def _assert_reopened(self):
        self.membership.refresh_from_db()
        self.assertIsNone(self.membership.left_date)
        self.assertEqual(
            OrganisationalUnitMember.objects.filter(
                unit=self.unit, member=self.person
            ).count(),
            1,
        )
        self.assertIn(self.consultant_role, self.membership.roles.all())

    def test_add_member_reopens(self):
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse("organisationalunit_add", kwargs={"slug": self.unit.slug}),
            {"member": self.person.pk},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self._assert_reopened()

    def test_add_member_still_refuses_current_member(self):
        self.membership.left_date = None
        self.membership.save()
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse("organisationalunit_add", kwargs={"slug": self.unit.slug}),
            {"member": self.person.pk},
        )
        self.assertFalse(resp.json()["form_is_valid"])

    def test_preload_reopens(self):
        self.client.force_login(self.manager)
        resp = self.client.post(self.preload_url(), {"email": self.person.email})
        self.assertTrue(resp.json()["form_is_valid"])
        self._assert_reopened()

    def test_csv_import_reopens(self):
        self.client.force_login(self.manager)
        f = SimpleUploadedFile(
            "members.csv", b"email\nleft@test.com\n", "text/csv"
        )
        self.client.post(self.import_url(), {"csv_file": f})
        self._assert_reopened()

    def test_ensure_lead_memberships_reopens(self):
        self.unit.leads.add(self.person)
        self.unit.ensure_lead_memberships()
        self._assert_reopened()

    def test_left_members_not_managers_or_notified(self):
        from jobtracker.models import OrganisationalUnitRole

        role = OrganisationalUnitRole.objects.filter(manage_role=True).first()
        self.membership.roles.add(role)
        self.assertNotIn(self.person, self.unit.get_managers())
        self.assertNotIn(self.person, unit_members(self.membership))


class RejoinTests(PreloadMemberBase):
    def setUp(self):
        super().setUp()
        self.person = User.objects.create_user(email="former@test.com", password="pw")
        self.membership = OrganisationalUnitMember.objects.create(
            unit=self.unit, member=self.person
        )
        self.membership.roles.add(self.consultant_role)
        self.membership.left_date = timezone.now() - timedelta(days=5)
        self.membership.save()
        assign_perm("jobtracker.view_organisationalunit", self.manager, self.unit)
        assign_perm("jobtracker.view_organisationalunit", self.outsider, self.unit)

    def _url(self):
        return reverse(
            "organisationalunit_rejoin_member",
            kwargs={"slug": self.unit.slug, "member_pk": self.membership.pk},
        )

    def test_rejoin_requires_manage_members(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self._url()).status_code, 403)
        self.membership.refresh_from_db()
        self.assertIsNotNone(self.membership.left_date)

    def test_rejoin_reopens_with_roles_and_perms(self):
        self.client.force_login(self.manager)
        resp = self.client.post(self._url())
        self.assertTrue(resp.json()["form_is_valid"])
        self.membership.refresh_from_db()
        self.assertIsNone(self.membership.left_date)
        self.assertTrue(get_user_perms(self.person, self.unit).exists())
        # Already back: a second Rejoin 404s.
        self.assertEqual(self.client.post(self._url()).status_code, 404)

    def test_team_table_lists_former_members_and_wording(self):
        self.client.force_login(self.manager)
        resp = self.client.get(
            reverse("organisationalunit_detail", kwargs={"slug": self.unit.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            [m.pk for m in resp.context["former_memberships"]], [self.membership.pk]
        )
        self.assertContains(resp, "Show former members (1)")
        self.assertContains(resp, "Show deactivated")
        self.assertNotContains(resp, "Show disabled")
        self.assertContains(resp, self._url())

    def test_rejoin_hidden_without_manage_members(self):
        self.client.force_login(self.outsider)
        resp = self.client.get(
            reverse("organisationalunit_detail", kwargs={"slug": self.unit.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, self._url())
