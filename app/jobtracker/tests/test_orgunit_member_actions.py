"""Tests for the org-unit team row actions: remove member and toggle lead."""
import json

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from jobtracker.models import (
    OrganisationalUnitMember,
    OrganisationalUnitRole,
)
from jobtracker.views import orgunit as orgunit_views
from .test_schedule_history import ScheduleHistoryBase


class OrgUnitMemberActionsBase(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        # actor drives the requests; superuser clears the guardian perm gate.
        self.actor.is_superuser = True
        self.actor.save()

        self.manager_role, _ = OrganisationalUnitRole.objects.get_or_create(
            name="Manager", defaults={"manage_role": True}
        )
        if not self.manager_role.manage_role:
            self.manager_role.manage_role = True
            self.manager_role.save()
        self.consultant_role, _ = OrganisationalUnitRole.objects.get_or_create(
            name="Consultant"
        )

        # `other` is an active member we act on.
        self.membership = OrganisationalUnitMember.objects.create(
            unit=self.unit, member=self.other
        )
        self.membership.roles.add(self.consultant_role)
        self.unit.sync_permissions()

    def _request(self, user=None):
        req = self.rf.post("/action")
        req.user = user or self.actor
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def _post(self, view, **kwargs):
        resp = view(self._request(), slug=self.unit.slug, **kwargs)
        return json.loads(resp.content)


class RemoveMemberTests(OrgUnitMemberActionsBase):
    def test_remove_soft_leaves_and_revokes_perms(self):
        self.other.user_permissions.clear()
        data = self._post(
            orgunit_views.organisationalunit_remove_member,
            member_pk=self.membership.pk,
        )
        self.assertTrue(data["form_is_valid"])

        self.membership.refresh_from_db()
        self.assertIsNotNone(self.membership.left_date)
        # Dropped from the active roster.
        self.assertNotIn(self.other, list(self.unit.get_activeMembers()))
        # Unit permissions revoked.
        from guardian.shortcuts import get_user_perms

        self.assertEqual(list(get_user_perms(self.other, self.unit)), [])

    def test_remove_clears_lead_status(self):
        self.unit.leads.add(self.other)
        self.unit.ensure_lead_memberships()
        self._post(
            orgunit_views.organisationalunit_remove_member,
            member_pk=self.membership.pk,
        )
        self.assertNotIn(self.other, list(self.unit.leads.all()))

    def test_cannot_remove_own_membership_unless_superuser(self):
        self.actor.is_superuser = False
        self.actor.save()
        # Give actor manage_members so it's the self-guard (not the perm gate) that blocks.
        from guardian.shortcuts import assign_perm

        self_ms = OrganisationalUnitMember.objects.create(
            unit=self.unit, member=self.actor
        )
        # Assign after creating the membership: member.save() runs
        # sync_permissions, which would otherwise strip a manually-granted perm.
        assign_perm("manage_members", self.actor, self.unit)
        # Refetch to clear guardian's per-instance permission cache.
        from chaotica_utils.models import User

        self.actor = User.objects.get(pk=self.actor.pk)
        resp = orgunit_views.organisationalunit_remove_member(
            self._request(user=self.actor),
            slug=self.unit.slug,
            member_pk=self_ms.pk,
        )
        self.assertEqual(resp.status_code, 400)


class ToggleLeadTests(OrgUnitMemberActionsBase):
    def test_make_lead_grants_management_role(self):
        self.assertNotIn(self.other, list(self.unit.leads.all()))
        data = self._post(
            orgunit_views.organisationalunit_toggle_lead,
            member_pk=self.membership.pk,
        )
        self.assertTrue(data["form_is_valid"])
        self.assertIn(self.other, list(self.unit.leads.all()))
        self.membership.refresh_from_db()
        self.assertIn(self.manager_role, list(self.membership.roles.all()))

    def test_toggle_off_removes_lead_and_management_role(self):
        self.unit.leads.add(self.other)
        self.unit.ensure_lead_memberships()
        self.membership.refresh_from_db()
        self.assertIn(self.manager_role, list(self.membership.roles.all()))
        self._post(
            orgunit_views.organisationalunit_toggle_lead,
            member_pk=self.membership.pk,
        )
        self.assertNotIn(self.other, list(self.unit.leads.all()))
        self.membership.refresh_from_db()
        self.assertNotIn(self.manager_role, list(self.membership.roles.all()))
