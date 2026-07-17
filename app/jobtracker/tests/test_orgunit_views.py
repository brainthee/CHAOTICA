"""Tests for the organisational unit detail page partials."""
import json
from datetime import timedelta

from django.test import RequestFactory, override_settings
from django.utils import timezone

from jobtracker.models import (
    Phase,
    OrganisationalUnitMember,
    OrganisationalUnitRole,
)
from jobtracker.enums import PhaseStatuses
from jobtracker.views import orgunit as orgunit_views
from .test_schedule_history import ScheduleHistoryBase


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class OrgUnitBoardPartialTests(ScheduleHistoryBase):
    """The Delivered/Completed columns are bounded to the last 30 days."""

    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        now = timezone.now()

        # A recently delivered phase (within window) should appear.
        self.recent = Phase.objects.create(job=self.job, title="Recently Delivered")
        self.recent.status = PhaseStatuses.DELIVERED
        self.recent.actual_delivery_date = now - timedelta(days=5)
        self.recent.save()

        # An old delivered phase (outside window) should be excluded.
        self.old = Phase.objects.create(job=self.job, title="Ancient Delivery")
        self.old.status = PhaseStatuses.DELIVERED
        self.old.actual_delivery_date = now - timedelta(days=90)
        self.old.save()

    def _board_html(self):
        req = self.rf.get("/board", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        req.user = self.actor  # actor is a superuser in the base fixtures
        resp = orgunit_views.orgunit_board_partial(req, slug=self.unit.slug)
        return json.loads(resp.content)["html"]

    def test_recent_delivered_phase_included(self):
        self.assertIn("Recently Delivered", self._board_html())

    def test_old_delivered_phase_excluded(self):
        self.assertNotIn("Ancient Delivery", self._board_html())


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class OrgUnitConsultantUtilisationTests(ScheduleHistoryBase):
    """Utilisation is scoped to consultants — the only members who get booked."""

    def setUp(self):
        super().setUp()
        consultant_role, _ = OrganisationalUnitRole.objects.get_or_create(
            name="Consultant"
        )
        manager_role, _ = OrganisationalUnitRole.objects.get_or_create(name="Manager")

        self.consultant_ms = OrganisationalUnitMember.objects.create(
            unit=self.unit, member=self.actor
        )
        self.consultant_ms.roles.add(consultant_role)
        self.manager_ms = OrganisationalUnitMember.objects.create(
            unit=self.unit, member=self.other
        )
        self.manager_ms.roles.add(manager_role)

    def test_consultant_ids_matched_by_role_name(self):
        ids = self.unit.get_consultant_ids()
        self.assertIn(self.actor.pk, ids)
        self.assertNotIn(self.other.pk, ids)

    def test_member_utilisation_lists_consultants_only(self):
        stats = self.unit.get_stats()
        util_ids = {row["user_id"] for row in stats["member_utilisation"]}
        self.assertEqual(util_ids, {self.actor.pk})
        # Roster count still reflects everyone; consultants is the booked subset.
        self.assertEqual(stats["summary"]["active_members"], 2)
        self.assertEqual(stats["summary"]["consultants"], 1)
