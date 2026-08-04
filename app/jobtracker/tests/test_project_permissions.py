"""Tests for the project permission model wired into the global role tables.

Projects are gated by the default Django model permissions
(``view_project`` / ``add_project`` / ``change_project`` / ``delete_project``),
granted site-wide via the ``GlobalRoles.PERMISSIONS`` groups (there is no
role inheritance, so each role lists what it needs explicitly). The intended
matrix is:

* everyone (``User`` + all elevated roles): read all projects,
* Sales + Managers + Admin: create & edit,
* Managers + Admin: delete.

The custom SessionMiddleware rejects requests without HTTP_HOST, so the test
client is constructed with ``HTTP_HOST='localhost'``.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings

from chaotica_utils.models import User, Group
from chaotica_utils.enums import GlobalRoles
from jobtracker.models import OrganisationalUnit, Project


def _global_group(role_int):
    """Fetch (and re-sync) the Global-role group for ``role_int``.

    Groups are created + synced on post_migrate, but we re-sync here so the test
    asserts against the *current* PERMISSIONS matrix regardless of ordering.
    """
    grp = Group.objects.get(
        name=settings.GLOBAL_GROUP_PREFIX + dict(GlobalRoles.CHOICES)[role_int]
    )
    grp.sync_global_permissions()
    return grp


class ProjectPermissionBase(TestCase):
    def setUp(self):
        # The first user created is force-promoted to superuser by User.save();
        # keep it aside so our actors are plain, non-superuser accounts.
        self.bootstrap = User.objects.create_user(
            email="root@test.com", password="pw12345"
        )
        self.unit = OrganisationalUnit.objects.create(name="Test Unit")
        self.project = Project.objects.create(
            title="RM mirrored project",
            unit=self.unit,
            created_by=self.bootstrap,
        )
        self.client = Client(HTTP_HOST="localhost")

    def _user_with_role(self, email, role_int):
        user = User.objects.create_user(email=email, password="pw12345")
        user.groups.add(_global_group(role_int))
        return User.objects.get(pk=user.pk)  # reset guardian per-request cache

    def detail_url(self):
        return reverse("project_detail", kwargs={"slug": self.project.slug})

    def update_url(self):
        return reverse("project_update", kwargs={"slug": self.project.slug})

    def delete_url(self):
        return reverse("project_delete", kwargs={"slug": self.project.slug})


class ProjectViewGateTests(ProjectPermissionBase):
    """End-to-end gating through the real (guardian-protected) views."""

    def test_user_role_can_view_and_create_but_not_edit(self):
        user = self._user_with_role("user@test.com", GlobalRoles.USER)
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("project_list")).status_code, 200)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        # Every user can now create projects...
        self.assertEqual(self.client.get(reverse("project_create")).status_code, 200)
        # ...but not edit or delete existing ones.
        self.assertEqual(self.client.get(self.update_url()).status_code, 403)
        self.assertEqual(self.client.get(self.delete_url()).status_code, 403)

    def test_sales_member_can_create_and_edit_not_delete(self):
        user = self._user_with_role("sales@test.com", GlobalRoles.SALES_MEMBER)
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("project_create")).status_code, 200)
        self.assertEqual(self.client.get(self.update_url()).status_code, 200)
        self.assertEqual(self.client.get(self.delete_url()).status_code, 403)

    def test_manager_can_delete(self):
        user = self._user_with_role("mgr@test.com", GlobalRoles.DELIVERY_MGR)
        self.client.force_login(user)

        self.assertEqual(self.client.get(self.update_url()).status_code, 200)
        self.assertEqual(self.client.get(self.delete_url()).status_code, 200)

    def test_no_global_role_is_denied(self):
        user = User.objects.create_user(email="nobody@test.com", password="pw12345")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 403)


class ProjectPermissionMatrixTests(ProjectPermissionBase):
    """Belt-and-braces: assert the role → permission wiring directly."""

    CASES = {
        GlobalRoles.USER: {"view": True, "add": True, "change": False, "delete": False},
        GlobalRoles.SERVICE_DELIVERY: {
            "view": True, "add": False, "change": False, "delete": False,
        },
        GlobalRoles.SALES_MEMBER: {
            "view": True, "add": True, "change": True, "delete": False,
        },
        GlobalRoles.SALES_MGR: {
            "view": True, "add": True, "change": True, "delete": False,
        },
        GlobalRoles.DELIVERY_MGR: {
            "view": True, "add": True, "change": True, "delete": True,
        },
        GlobalRoles.ADMIN: {"view": True, "add": True, "change": True, "delete": True},
    }

    def test_matrix(self):
        for role_int, expected in self.CASES.items():
            label = dict(GlobalRoles.CHOICES)[role_int]
            user = self._user_with_role("role{}@test.com".format(role_int), role_int)
            for action, allowed in expected.items():
                perm = "jobtracker.{}_project".format(action)
                self.assertEqual(
                    user.has_perm(perm),
                    allowed,
                    msg="{} should{} have {}".format(
                        label, "" if allowed else " NOT", perm
                    ),
                )
