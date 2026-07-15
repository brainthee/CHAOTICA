"""Regression tests for role permission syncing (see fix/role-permission-name-matching).

The original bug: ``OrganisationalUnitRole.sync_default_permissions`` matched a role
to its code definition by ``self.pk == UnitRoles constant`` and looked perms up via
``PERMISSIONS[pk-1]``. In production the role table's pks had drifted from the
enum constants, so every role was silently assigned another role's permission set
(e.g. the Scheduler role lost ``can_schedule_job``). These tests pin the behaviour
to NAME-based matching, which is resilient to pk drift.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase

from chaotica_utils.enums import UnitRoles
from jobtracker.models import OrganisationalUnit
from jobtracker.models.orgunit import OrganisationalUnitRole


def _perm_codenames(role):
    return set(role.permissions.values_list("codename", flat=True))


def _expected_codenames(name):
    return set(
        p.split(".")[-1]
        for p in (UnitRoles.get_default_permissions_for_role(name) or [])
        if p
    )


class RolePermissionSyncTests(TestCase):
    def test_helper_matches_by_name_not_pk(self):
        # Scheduler must carry can_schedule_job regardless of any pk.
        perms = UnitRoles.get_default_permissions_for_role("Scheduler")
        self.assertIn("jobtracker.can_schedule_job", perms)
        # Service Delivery and Manager too.
        self.assertIn(
            "jobtracker.can_schedule_job",
            UnitRoles.get_default_permissions_for_role("Service Delivery"),
        )
        self.assertIn(
            "jobtracker.can_schedule_job",
            UnitRoles.get_default_permissions_for_role("Manager"),
        )

    def test_helper_returns_none_for_unknown_role(self):
        self.assertIsNone(
            UnitRoles.get_default_permissions_for_role("Totally Made Up Role")
        )

    def test_sync_correct_when_pk_matches_constant(self):
        role = OrganisationalUnitRole.objects.get(name="Scheduler")
        role.permissions.clear()
        self.assertTrue(role.sync_default_permissions())
        self.assertEqual(_perm_codenames(role), _expected_codenames("Scheduler"))

    def test_sync_correct_even_when_pk_drifts(self):
        """The core regression: a role whose pk != its enum constant must still
        receive its OWN permissions, not those of the role at PERMISSIONS[pk-1]."""
        # Recreate the Scheduler role with a pk well clear of any enum constant.
        OrganisationalUnitRole.objects.filter(name="Scheduler").delete()
        role = OrganisationalUnitRole.objects.create(pk=9999, name="Scheduler")

        self.assertTrue(role.sync_default_permissions())
        self.assertIn("can_schedule_job", _perm_codenames(role))
        self.assertEqual(_perm_codenames(role), _expected_codenames("Scheduler"))

    def test_sync_leaves_unknown_role_untouched(self):
        custom = OrganisationalUnitRole.objects.create(name="Custom Ops Role")
        perm = Permission.objects.get(codename="can_schedule_job")
        custom.permissions.add(perm)
        # Not a known default role -> returns False and does not clear perms.
        self.assertFalse(custom.sync_default_permissions())
        self.assertIn("can_schedule_job", _perm_codenames(custom))

    def test_unit_sync_grants_object_perm_with_drifted_pk(self):
        """End-to-end: a member of a role with a drifted pk still gets the
        guardian object permission after the unit re-syncs."""
        from chaotica_utils.models import User
        from jobtracker.models.orgunit import OrganisationalUnitMember

        OrganisationalUnitRole.objects.filter(name="Scheduler").delete()
        role = OrganisationalUnitRole.objects.create(pk=8888, name="Scheduler")
        role.sync_default_permissions()

        unit = OrganisationalUnit.objects.create(name="Sync Test Unit")
        user = User.objects.create_user(email="member@test.com", password="pw12345")
        member = OrganisationalUnitMember.objects.create(unit=unit, member=user)
        member.roles.add(role)

        unit.sync_permissions()
        user = User.objects.get(pk=user.pk)  # reset guardian perm cache
        self.assertTrue(user.has_perm("jobtracker.can_schedule_job", unit))
