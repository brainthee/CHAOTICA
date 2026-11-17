"""Tests for the read-only permissions-visibility UI: the role/permission
matrix page, the admin-only profile permissions panel, and the grouping helper.
"""

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import Permission

from chaotica_utils.enums import GlobalRoles
from chaotica_utils.models import User, Group
from chaotica_utils.utils import group_permissions


def _give_user_role(user):
    """Add a user to the baseline ``Global: User`` group so they can view
    profiles (``UserDetailView`` requires any global role)."""
    group, _ = Group.objects.get_or_create(
        name=settings.GLOBAL_GROUP_PREFIX + GlobalRoles.CHOICES[GlobalRoles.USER][1]
    )
    user.groups.add(group)


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class PermissionsMatrixViewTests(TestCase):
    def setUp(self):
        # First create_user is auto-promoted to superuser + Global: Admin group.
        self.admin = User.objects.create_user(
            email="admin@test.com", password="pw12345"
        )
        self.user = User.objects.create_user(email="user@test.com", password="pw12345")
        _give_user_role(self.user)

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse("permissions_matrix"), HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp["Location"])

    def test_non_admin_forbidden(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("permissions_matrix"), HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 403)

    def test_admin_gets_matrix(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("permissions_matrix"), HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("global_matrix", resp.context)
        self.assertIn("unit_matrix", resp.context)
        # Global Admin role column should include the manage_user permission.
        global_matrix = resp.context["global_matrix"]
        labels = [c["label"] for c in global_matrix["columns"]]
        self.assertIn("Admin", labels)


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class ProfilePermissionsPanelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com", password="pw12345"
        )
        self.user = User.objects.create_user(email="user@test.com", password="pw12345")
        _give_user_role(self.user)

    def test_admin_sees_permissions_panel(self):
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("user_profile", kwargs={"email": self.user.email}),
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["can_view_permissions"])
        self.assertIn("user_permissions", resp.context)

    def test_non_admin_does_not_see_permissions_panel(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("user_profile", kwargs={"email": self.admin.email}),
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_view_permissions"])
        self.assertNotIn("user_permissions", resp.context)

    def test_panel_resolves_unit_object_permissions(self):
        # Give the user a unit membership with a role so the guardian
        # object-permission path (get_user_perms) is exercised end-to-end.
        from jobtracker.models import (
            OrganisationalUnit,
            OrganisationalUnitMember,
            OrganisationalUnitRole,
        )

        unit = OrganisationalUnit.objects.create(name="Test Unit", slug="test-unit")
        role = OrganisationalUnitRole.objects.get(name="Consultant")
        ms = OrganisationalUnitMember.objects.create(unit=unit, member=self.user)
        ms.roles.add(role)
        unit.sync_permissions()

        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("user_profile", kwargs={"email": self.user.email}),
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        units = resp.context["user_permissions"]["units"]
        self.assertEqual(len(units), 1)
        # Consultant grants can_view_jobs on the unit; it should resolve to a
        # grouped, humanised permission entry.
        all_codenames = [
            perm["codename"]
            for perms in units[0]["permissions"].values()
            for perm in perms
        ]
        self.assertIn("can_view_jobs", all_codenames)


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class ScheduleHistoryTabTests(TestCase):
    """The Schedule History tab is gated on being able to view the person's
    schedule, and renders the ScheduleAction-backed partial (not the old
    simple-history timeline)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com", password="pw12345"
        )
        self.user = User.objects.create_user(email="user@test.com", password="pw12345")
        _give_user_role(self.user)

    def test_tab_shown_to_schedule_viewer(self):
        self.client.force_login(self.admin)  # superuser can view any schedule
        resp = self.client.get(
            reverse("user_profile", kwargs={"email": self.user.email}),
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["can_view_schedule"])
        content = resp.content.decode()
        self.assertIn("schedule-history-root", content)
        self.assertIn("/api/v1/schedule/actions/", content)
        # The feed is scoped to the profile's user, not the viewer.
        self.assertIn('data-user-pk="%d"' % self.user.pk, content)
        # The old experimental simple-history timeline is gone.
        self.assertNotIn("should only be used as a rough guide", content)

    def test_tab_hidden_without_schedule_view(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("user_profile", kwargs={"email": self.admin.email}),
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_view_schedule"])
        self.assertNotIn("schedule-history-root", resp.content.decode())


class GroupPermissionsHelperTests(TestCase):
    def test_groups_by_app_and_model_with_names(self):
        grouped = group_permissions(Permission.objects.all())
        self.assertTrue(len(grouped) > 0)
        # Keys are "app · model"; values are dicts with codename + name.
        first_key = next(iter(grouped))
        self.assertIn(" · ", first_key)
        row = grouped[first_key][0]
        self.assertIn("codename", row)
        self.assertIn("name", row)

    def test_empty_queryset_returns_empty(self):
        grouped = group_permissions(Permission.objects.none())
        self.assertEqual(len(grouped), 0)
