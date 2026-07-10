"""Tests for the unit-member pre-load / CSV-import onboarding feature.

Covers the single pre-load flow, the CSV bulk import + template download, the
site-role authority gate (unit managers may only grant the default site role),
the email-domain allowlist, and the ``manage_members`` permission gate.

The custom SessionMiddleware rejects requests without HTTP_HOST, so the test
client is constructed with ``HTTP_HOST='localhost'``.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from guardian.shortcuts import assign_perm
from constance.test import override_config

from chaotica_utils.models import User, Group
from chaotica_utils.enums import GlobalRoles, UnitRoles
from jobtracker.models import (
    OrganisationalUnit,
    OrganisationalUnitMember,
    OrganisationalUnitRole,
)


def _global_group(role_int):
    return Group.objects.get(
        name=settings.GLOBAL_GROUP_PREFIX + dict(GlobalRoles.CHOICES)[role_int]
    )


class PreloadMemberBase(TestCase):
    def setUp(self):
        # The very first user created is force-promoted to superuser by the
        # User.save() bootstrap; keep it out of the way so our actors are plain.
        self.bootstrap = User.objects.create_user(
            email="root@test.com", password="pw12345"
        )
        self.unit = OrganisationalUnit.objects.create(name="Test Unit")

        # Unit manager: object-level manage_members, but NO global manage_user.
        self.manager = User.objects.create_user(
            email="mgr@test.com", password="pw12345"
        )
        assign_perm("jobtracker.manage_members", self.manager, self.unit)

        # Admin: global manage_user + manage_members on the unit.
        self.admin = User.objects.create_user(
            email="admin@test.com", password="pw12345"
        )
        assign_perm("chaotica_utils.manage_user", self.admin)
        assign_perm("jobtracker.manage_members", self.admin, self.unit)

        # Plain user with no unit perms.
        self.outsider = User.objects.create_user(
            email="nobody@test.com", password="pw12345"
        )

        self.consultant_role = OrganisationalUnitRole.objects.get(
            pk=UnitRoles.CONSULTANT
        )
        self.client = Client(HTTP_HOST="localhost")

    def preload_url(self):
        return reverse(
            "organisationalunit_preload_member", kwargs={"slug": self.unit.slug}
        )

    def import_url(self):
        return reverse(
            "organisationalunit_import_members", kwargs={"slug": self.unit.slug}
        )


class SinglePreloadTests(PreloadMemberBase):
    def test_manager_preload_creates_active_user_with_default_role(self):
        self.client.force_login(self.manager)
        resp = self.client.post(
            self.preload_url(),
            {
                "email": "newbie@test.com",
                "first_name": "New",
                "last_name": "Bie",
                "unit_roles": [self.consultant_role.pk],
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])

        user = User.objects.get(email="newbie@test.com")
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        # Default "User" global role assigned
        self.assertIn(_global_group(GlobalRoles.USER), user.groups.all())
        # Unit membership + role
        membership = OrganisationalUnitMember.objects.get(unit=self.unit, member=user)
        self.assertIn(self.consultant_role, membership.roles.all())
        self.assertEqual(membership.inviter, self.manager)

    def test_manager_cannot_grant_elevated_site_role(self):
        self.client.force_login(self.manager)
        admin_group = _global_group(GlobalRoles.ADMIN)
        resp = self.client.post(
            self.preload_url(),
            {
                "email": "sneaky@test.com",
                "site_role": admin_group.pk,  # should be ignored for managers
                "unit_roles": [self.consultant_role.pk],
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])
        user = User.objects.get(email="sneaky@test.com")
        self.assertNotIn(admin_group, user.groups.all())
        self.assertIn(_global_group(GlobalRoles.USER), user.groups.all())

    def test_admin_can_grant_elevated_site_role(self):
        self.client.force_login(self.admin)
        admin_group = _global_group(GlobalRoles.ADMIN)
        resp = self.client.post(
            self.preload_url(),
            {
                "email": "boss@test.com",
                "site_role": admin_group.pk,
                "unit_roles": [self.consultant_role.pk],
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])
        user = User.objects.get(email="boss@test.com")
        self.assertIn(admin_group, user.groups.all())

    def test_existing_user_added_without_touching_site_role(self):
        existing = User.objects.create_user(
            email="existing@test.com", password="pw12345"
        )
        sales_group = _global_group(GlobalRoles.SALES_MEMBER)
        existing.groups.add(sales_group)

        self.client.force_login(self.manager)
        resp = self.client.post(
            self.preload_url(),
            {
                "email": "existing@test.com",
                "unit_roles": [self.consultant_role.pk],
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])
        existing.refresh_from_db()
        # Site role untouched; no default User role forced onto an existing user
        self.assertIn(sales_group, existing.groups.all())
        self.assertNotIn(_global_group(GlobalRoles.USER), existing.groups.all())
        self.assertTrue(
            OrganisationalUnitMember.objects.filter(
                unit=self.unit, member=existing
            ).exists()
        )

    @override_config(ALLOWED_SIGNUP_EMAIL_DOMAINS="allowed.com")
    def test_domain_allowlist_blocks_and_permits(self):
        self.client.force_login(self.manager)
        # Blocked domain
        resp = self.client.post(
            self.preload_url(),
            {"email": "x@blocked.com", "unit_roles": [self.consultant_role.pk]},
        )
        self.assertFalse(resp.json()["form_is_valid"])
        self.assertFalse(User.objects.filter(email="x@blocked.com").exists())
        # Permitted domain
        resp = self.client.post(
            self.preload_url(),
            {"email": "y@allowed.com", "unit_roles": [self.consultant_role.pk]},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertTrue(User.objects.filter(email="y@allowed.com").exists())

    def test_permission_gate_blocks_non_manager(self):
        self.client.force_login(self.outsider)
        resp = self.client.post(
            self.preload_url(),
            {"email": "z@test.com", "unit_roles": [self.consultant_role.pk]},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(User.objects.filter(email="z@test.com").exists())


class CsvImportTests(PreloadMemberBase):
    def _upload(self, text, **extra):
        f = SimpleUploadedFile("members.csv", text.encode("utf-8"), "text/csv")
        data = {"csv_file": f}
        data.update(extra)
        return self.client.post(self.import_url(), data)

    def test_template_download_headers(self):
        self.client.force_login(self.manager)
        resp = self.client.get(
            reverse("download_unit_members_template", kwargs={"slug": self.unit.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        first_line = resp.content.decode("utf-8").splitlines()[0]
        self.assertEqual(first_line, "email,first_name,last_name,site_role,unit_roles")

    def test_import_creates_members_and_reports_errors(self):
        self.client.force_login(self.manager)
        csv_text = (
            "email,first_name,last_name,site_role,unit_roles\n"
            "one@test.com,One,Uno,,Consultant\n"
            "two@test.com,Two,Dos,,Scoper;Consultant\n"
            "three@test.com,Bad,Role,,NotARealRole\n"
        )
        resp = self._upload(csv_text)
        # Redirects to the unit detail on any success
        self.assertEqual(resp.status_code, 302)

        self.assertTrue(
            OrganisationalUnitMember.objects.filter(
                unit=self.unit, member__email="one@test.com"
            ).exists()
        )
        two = OrganisationalUnitMember.objects.get(
            unit=self.unit, member__email="two@test.com"
        )
        role_names = set(two.roles.values_list("name", flat=True))
        self.assertTrue({"Scoper", "Consultant"}.issubset(role_names))
        # Bad role row skipped, user not created
        self.assertFalse(User.objects.filter(email="three@test.com").exists())

    def test_import_missing_email_column_rejected(self):
        self.client.force_login(self.manager)
        resp = self._upload("first_name,last_name\nA,B\n")
        # Bounces back to the import page (redirect), nothing created
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            OrganisationalUnitMember.objects.filter(unit=self.unit).count(), 0
        )

    def test_import_permission_gate(self):
        self.client.force_login(self.outsider)
        resp = self._upload("email\nfoo@test.com\n")
        self.assertEqual(resp.status_code, 403)


class DomainValidatorUnitTests(TestCase):
    """Direct tests of the reusable domain validator."""

    def test_blank_allows_any(self):
        from chaotica_utils.utils import email_domain_allowed

        with override_config(ALLOWED_SIGNUP_EMAIL_DOMAINS=""):
            self.assertTrue(email_domain_allowed("anyone@anywhere.com"))

    def test_case_insensitive_match(self):
        from chaotica_utils.utils import email_domain_allowed

        with override_config(ALLOWED_SIGNUP_EMAIL_DOMAINS="Example.com, Other.org"):
            self.assertTrue(email_domain_allowed("Bob@EXAMPLE.COM"))
            self.assertFalse(email_domain_allowed("bob@nope.com"))
