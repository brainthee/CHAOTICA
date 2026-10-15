"""T-10: only Schedulers and Managers schedule; Service Delivery doesn't.

SD keeps support-team management (gated on ``manage_members``), can't hand
out the Scheduler role (``can_schedule_job`` is a privileged perm), and gets a
read-only scheduler. Roles are the real default roles, synced from code.
"""
import json
from datetime import timedelta

from django.test import Client, override_settings
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.models import OrganisationalUnit, OrganisationalUnitMember, TimeSlot
from jobtracker.models.orgunit import OrganisationalUnitRole
from jobtracker.models.job import JobSupportTeamRole
from jobtracker.utils import user_has_unit_perms
from .test_schedule_history import ScheduleHistoryBase


def _role(name):
    role = OrganisationalUnitRole.objects.get(name=name)
    role.sync_default_permissions()
    return role


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class SchedulingRoleTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        self.users = {}
        for key, role in [
            ("sd", "Service Delivery"),
            ("manager", "Manager"),
            ("scheduler", "Scheduler"),
        ]:
            user = User.objects.create_user(email=f"{key}@test.com", password="pw12345")
            ms = OrganisationalUnitMember.objects.create(unit=self.unit, member=user)
            ms.roles.add(_role(role))
            self.users[key] = user
        # The slot owner is a plain consultant in the unit, so internal slots are
        # governed by this unit.
        ms = OrganisationalUnitMember.objects.create(unit=self.unit, member=self.other)
        ms.roles.add(_role("Consultant"))
        self.unit.sync_permissions()

    def _client(self, key):
        c = Client(HTTP_HOST="localhost")
        c.force_login(User.objects.get(pk=self.users[key].pk))
        return c

    def _move_payload(self, slot):
        return {
            "user": slot.user_id,
            "start": (slot.start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "end": (slot.end + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        }

    # ---- slot edit endpoints ----

    def test_sd_cannot_move_edit_or_delete_slots(self):
        slot = self._internal_slot(user=self.other)
        c = self._client("sd")
        url = reverse("change_scheduler_slot_date", kwargs={"pk": slot.pk})
        self.assertEqual(c.post(url, self._move_payload(slot)).status_code, 403)
        url = reverse("change_scheduler_slot", kwargs={"pk": slot.pk})
        self.assertEqual(c.post(url, self._move_payload(slot)).status_code, 403)
        url = reverse("delete_scheduler_slot", kwargs={"pk": slot.pk})
        self.assertEqual(c.post(url).status_code, 403)
        self.assertTrue(TimeSlot.objects.filter(pk=slot.pk).exists())

    def test_sd_cannot_create_slots(self):
        c = self._client("sd")
        resp = c.get(reverse("create_scheduler_internal_slot"))
        self.assertEqual(resp.status_code, 403)
        resp = c.get(reverse("create_scheduler_phase_slot"))
        self.assertEqual(resp.status_code, 403)

    def test_manager_and_scheduler_can_move_slots(self):
        for key in ("manager", "scheduler"):
            slot = self._internal_slot(user=self.other)
            c = self._client(key)
            url = reverse("change_scheduler_slot_date", kwargs={"pk": slot.pk})
            resp = c.post(url, self._move_payload(slot))
            self.assertEqual(resp.status_code, 200, key)
            self.assertTrue(json.loads(resp.content)["form_is_valid"], key)

    # ---- support teams stay with SD + Manager ----

    def test_sd_can_still_manage_support_team(self):
        c = self._client("sd")
        resp = c.get(reverse("job_support_team_add", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 200)
        role = JobSupportTeamRole.objects.create(job=self.job, user=self.other)
        resp = c.get(
            reverse(
                "job_support_team_edit", kwargs={"slug": self.job.slug, "pk": role.pk}
            )
        )
        self.assertEqual(resp.status_code, 200)

    def test_scheduler_cannot_manage_support_team(self):
        c = self._client("scheduler")
        resp = c.get(reverse("job_support_team_add", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 403)

    # ---- role ceiling ----

    def test_sd_cannot_assign_scheduler_role(self):
        sd = User.objects.get(pk=self.users["sd"].pk)
        names = set(self.unit.assignable_roles(sd).values_list("name", flat=True))
        self.assertNotIn("Scheduler", names)
        self.assertNotIn("Manager", names)
        manager = User.objects.get(pk=self.users["manager"].pk)
        names = set(self.unit.assignable_roles(manager).values_list("name", flat=True))
        self.assertIn("Scheduler", names)

    # ---- any-membership gate ----

    def test_gate_passes_on_any_membership_not_just_first(self):
        # First membership: a unit where the scheduler can't schedule.
        first = OrganisationalUnit.objects.create(name="AAA First Unit")
        user = User.objects.create_user(email="multi@test.com", password="pw12345")
        ms = OrganisationalUnitMember.objects.create(unit=first, member=user)
        ms.roles.add(_role("Consultant"))
        ms = OrganisationalUnitMember.objects.create(unit=self.unit, member=user)
        ms.roles.add(_role("Scheduler"))
        first.sync_permissions()
        self.unit.sync_permissions()
        user = User.objects.get(pk=user.pk)
        self.assertEqual(user.unit_memberships.first().unit, first)
        self.assertTrue(user_has_unit_perms(user, "jobtracker.can_schedule_job"))
        c = Client(HTTP_HOST="localhost")
        c.force_login(user)
        self.assertEqual(c.get(reverse("create_scheduler_internal_slot")).status_code, 200)

    def test_gate_ignores_left_memberships(self):
        user = User.objects.get(pk=self.users["scheduler"].pk)
        from django.utils import timezone

        OrganisationalUnitMember.objects.filter(member=user).update(
            left_date=timezone.now() - timedelta(days=1)
        )
        user = User.objects.get(pk=user.pk)
        self.assertFalse(user_has_unit_perms(user, "jobtracker.can_schedule_job"))

    # ---- read-only scheduler UI ----

    def test_scheduler_pages_read_only_for_sd(self):
        c = self._client("sd")
        pages = [
            reverse("view_scheduler") + "?nofilter=1",
            reverse("job_schedule", kwargs={"slug": self.job.slug}),
            reverse(
                "phase_schedule",
                kwargs={"job_slug": self.job.slug, "slug": self.phase.slug},
            ),
        ]
        for url in pages:
            resp = c.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertTrue(resp.context["sched_readonly"], url)
            self.assertContains(resp, "readonly: true")
            self.assertNotContains(resp, 'id="btnModeSelect"')

    def test_scheduler_pages_editable_for_scheduler(self):
        c = self._client("scheduler")
        resp = c.get(reverse("job_schedule", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["sched_readonly"])
        self.assertContains(resp, "readonly: false")
        self.assertContains(resp, 'id="btnModeSelect"')
