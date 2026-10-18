"""PolicyContext (A1) and the workflow description."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.middleware.common import set_current_user
from chaotica_utils.models import User
from jobtracker import workflow
from jobtracker.enums import DefaultTimeSlotTypes, JobStatuses, PhaseStatuses
from jobtracker.models import Job, Phase, TimeSlot, TimeSlotType
from jobtracker.policy import PolicyContext

from .helpers import ApiV1TestCase, leave_unit, make_member


class PolicyContextTests(ApiV1TestCase):
    def test_unit_lookups_are_memoised(self):
        policy = PolicyContext(self.normal)
        policy.unit_ids("jobtracker.can_view_jobs")
        with self.assertNumQueries(0):
            policy.unit_ids("can_view_jobs")  # same perm, either spelling
            policy.units("jobtracker.can_view_jobs")

    def test_job_scope_matches_legacy_union(self):
        job = self.make_job(account_manager=self.normal)
        self.make_job()
        scoped = PolicyContext(self.normal).scope("job.view", Job.objects.all())
        expected = set(
            Job.objects.jobs_with_unit_permission(
                self.normal, "jobtracker.can_view_jobs"
            ).values_list("pk", flat=True)
        ) | set(Job.objects.jobs_for_user(self.normal).values_list("pk", flat=True))
        self.assertEqual(set(scoped.values_list("pk", flat=True)), expected)
        self.assertIn(job.pk, expected)

    def test_unknown_action_raises(self):
        with self.assertRaises(KeyError):
            PolicyContext(self.normal).can("job.teleport")

    def test_timeslots_of_leavers_hidden(self):
        """Security: v1 /timeslots/ used to show slots of people who had left
        the viewer's unit; it now matches the scheduler."""
        job = self.make_job()
        viewer = make_member(
            User.objects.create_user(email="sched@example.com", password="pw"),
            job.unit,
            roles=("Consultant",),
        )
        leaver = make_member(
            User.objects.create_user(email="leaver@example.com", password="pw"),
            job.unit,
        )
        start = timezone.now().replace(microsecond=0)
        slot = TimeSlot.objects.create(
            user=leaver,
            slot_type=TimeSlotType.get_builtin_object(
                DefaultTimeSlotTypes.INTERNAL_PROJECT
            ),
            start=start,
            end=start + timedelta(hours=1),
        )
        client = self.as_user(viewer)
        ids = {r["id"] for r in client.get("/api/v1/timeslots/").json()["results"]}
        self.assertIn(slot.pk, ids)
        leave_unit(leaver, job.unit)
        ids = {r["id"] for r in client.get("/api/v1/timeslots/").json()["results"]}
        self.assertNotIn(slot.pk, ids)

    def test_global_capabilities_shape(self):
        caps = PolicyContext(self.superuser).global_capabilities()
        self.assertTrue(caps["is_global_admin"])
        self.assertTrue(all(isinstance(v, bool) for v in caps.values()))


class WorkflowTableTests(TestCase):
    def test_every_fsm_transition_is_described(self):
        for model, table in (
            (Job, workflow.JOB_TRANSITIONS),
            (Phase, workflow.PHASE_TRANSITIONS),
        ):
            names = {
                t.name
                for t in model._meta.get_field("status").get_all_transitions(model)
            }
            missing = names - set(table) - workflow.INTERNAL_TRANSITIONS
            self.assertFalse(missing, f"{model.__name__} transitions without a label")
            self.assertFalse(
                set(table) - names, "labels for transitions that don't exist"
            )

    def test_every_status_has_a_step_or_is_off_path(self):
        off_path_job = {JobStatuses.LOST, JobStatuses.DELETED}
        on_path = {s for step in workflow.JOB_STEPS for s in step.statuses}
        for value, _ in JobStatuses.CHOICES:
            self.assertTrue(value in on_path or value in off_path_job, value)
        off_path_phase = {
            PhaseStatuses.CANCELLED,
            PhaseStatuses.POSTPONED,
            PhaseStatuses.DELETED,
        }
        on_path = {s for step in workflow.PHASE_STEPS for s in step.statuses}
        for value, _ in PhaseStatuses.CHOICES:
            self.assertTrue(value in on_path or value in off_path_phase, value)


class WorkflowBlockTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(set_current_user, None)

    def test_steps_and_transitions(self):
        job = self.make_job()
        Job.objects.filter(pk=job.pk).update(status=JobStatuses.PENDING_SCOPE)
        job.refresh_from_db()
        set_current_user(self.superuser)
        block = workflow.workflow_block(PolicyContext(self.superuser), job)
        states = {s["label"]: s["state"] for s in block["steps"]}
        self.assertEqual(states["Draft"], "done")
        self.assertEqual(states["Scoping"], "current")
        self.assertEqual(states["Complete"], "todo")
        names = {t["name"] for t in block["transitions"]}
        self.assertIn("to_scoping", names)
        self.assertNotIn("to_reopen_for_phase", names)
        scoping = next(t for t in block["transitions"] if t["name"] == "to_scoping")
        self.assertTrue(scoping["allowed"])
        self.assertEqual(scoping["target"], JobStatuses.SCOPING)

    def test_reopen_shares_target_but_not_name(self):
        job = self.make_job()
        Job.objects.filter(pk=job.pk).update(status=JobStatuses.COMPLETED)
        job.refresh_from_db()
        block = workflow.workflow_block(PolicyContext(self.normal), job)
        reopen = next(t for t in block["transitions"] if t["name"] == "to_reopen")
        self.assertEqual(reopen["target"], JobStatuses.SCOPING)
        self.assertTrue(reopen["needs_reason"])
        self.assertFalse(reopen["allowed"])  # normal can't update this job

    def test_off_path_status_has_no_current_step(self):
        job = self.make_job()
        Job.objects.filter(pk=job.pk).update(status=JobStatuses.LOST)
        job.refresh_from_db()
        steps = workflow.steps(job)
        self.assertNotIn("current", {s["state"] for s in steps})


class WorkflowButtonsTests(ApiV1TestCase):
    """The job/phase pages render their status buttons from workflow.py."""

    def test_job_buttons_and_menu(self):
        job = self.make_job()
        Job.objects.filter(pk=job.pk).update(status=JobStatuses.PENDING_SCOPE)
        self.client.force_login(self.superuser)
        page = self.client.get(job.get_absolute_url()).content.decode()
        self.assertIn("Begin Scoping", page)
        self.assertIn(
            reverse("job_update_workflow", args=[job.slug, JobStatuses.SCOPING]), page
        )
        self.assertIn("Close as Lost", page)
        # Transitions the page never offered by hand stay off it.
        self.assertNotIn("Start Job", page)

    def test_return_to_scoping_label(self):
        job = self.make_job()
        Job.objects.filter(pk=job.pk).update(status=JobStatuses.SCOPING_COMPLETE)
        job.refresh_from_db()
        labels = {
            t["name"]: t["label"]
            for t in workflow.available_transitions(PolicyContext(self.superuser), job)
        }
        self.assertEqual(labels["to_scoping"], "Return to Scoping")

    def test_phase_buttons_hidden_without_update_permission(self):
        job = self.make_job()
        phase = self.make_phase(job)
        Phase.objects.filter(pk=phase.pk).update(status=PhaseStatuses.PENDING_SCHED)
        outsider = User.objects.create_user(email="guest@example.com", password="pw")
        self.assertEqual(
            [
                t
                for t in workflow.available_transitions(PolicyContext(outsider), phase)
                if t["allowed"]
            ],
            [],
        )
        self.client.force_login(self.superuser)
        page = self.client.get(phase.get_absolute_url()).content.decode()
        self.assertIn("Confirm Schedule", page)

    def test_bulk_modal_uses_fsm(self):
        job = self.make_job()
        phase = self.make_phase(job)
        Phase.objects.filter(pk=phase.pk).update(status=PhaseStatuses.PENDING_SCHED)
        self.client.force_login(self.superuser)
        resp = self.client.get(
            reverse(
                "phases_bulk_workflow_modal",
                args=[job.slug, PhaseStatuses.SCHEDULED_CONFIRMED],
            )
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(phase.title, resp.json()["html_form"])
