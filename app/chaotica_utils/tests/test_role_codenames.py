"""Every permission named by a role definition must exist.

Role syncs skip unknown codenames (logging an error), so a typo silently drops
the grant - e.g. ``view_users_qualification`` vs ``..._qualifications``. This
catches it in CI instead."""

from django.contrib.auth.models import Permission
from django.test import TestCase

from chaotica_utils.enums import GlobalRoles, UnitRoles


class RoleCodenameTests(TestCase):
    def _missing(self, permissions):
        missing = []
        for role, perms in permissions:
            for perm in perms:
                if not perm:
                    continue
                app_label, _, codename = perm.rpartition(".")
                if not app_label:
                    missing.append((role, perm, "no app label"))
                elif not Permission.objects.filter(
                    content_type__app_label=app_label, codename=codename
                ).exists():
                    missing.append((role, perm, "does not exist"))
        return missing

    def test_global_role_permissions_exist(self):
        self.assertEqual(self._missing(GlobalRoles.PERMISSIONS), [])

    def test_unit_role_permissions_exist(self):
        self.assertEqual(self._missing(UnitRoles.PERMISSIONS), [])
