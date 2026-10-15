"""Reopening completed jobs/phases, the "unfinished work on a completed job"
safety net, and the user-facing booking rule (what can be scheduled, and when
existing bookings can be moved)."""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import AuditCategory, AuditEvent, AuditVerb
from jobtracker import schedule_history
from jobtracker.enums import JobStatuses, PhaseStatuses
from jobtracker.models import Phase, ScheduleActionType, TimeSlot

from .test_job_phase_cascades import CascadeTestBase


def _workflow_events(obj):
    return AuditEvent.objects.filter(
        category=AuditCategory.WORKFLOW,
        verb=AuditVerb.STATUS_CHANGE,
        target_content_type=ContentType.objects.get_for_model(obj.__class__),
        target_id=str(obj.pk),
    )


class JobReopenTests(CascadeTestBase):
    def setUp(self):
        super().setUp()
        self.delivered = self._phase(PhaseStatuses.DELIVERED)
        self._set_job_status(JobStatuses.COMPLETED)
        self.http.force_login(self.actor)
        self.url = reverse(
            "job_update_workflow",
            kwargs={"slug": self.job.slug, "new_state": JobStatuses.SCOPING},
        )

    def test_reopen_goes_to_scoping_with_audited_reason(self):
        resp = self.http.post(self.url, {"reason": "New phase requested by client"})
        self.assertTrue(resp.json()["form_is_valid"])
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.SCOPING)
        event = _workflow_events(self.job).get()
        self.assertIn("Completed to Scoping", event.message)
        self.assertIn("New phase requested by client", event.message)
        # Delivered work is left alone.
        self.delivered.refresh_from_db()
        self.assertEqual(self.delivered.status, PhaseStatuses.DELIVERED)

    def test_reopen_requires_a_reason(self):
        resp = self.http.post(self.url, {"reason": "  "})
        self.assertFalse(resp.json().get("form_is_valid", False))
        self.assertIn("Please give a reason", resp.json()["html_form"])
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.COMPLETED)

    def test_reopen_modal_asks_for_reason(self):
        resp = self.http.get(self.url)
        self.assertIn('name="reason"', resp.json()["html_form"])

    def test_manual_complete_refused_while_a_phase_is_unfinished(self):
        self._set_job_status(JobStatuses.IN_PROGRESS)
        Phase.objects.create(job=self.job, title="QA", status=PhaseStatuses.QA_TECH)
        resp = self.http.post(
            reverse(
                "job_update_workflow",
                kwargs={"slug": self.job.slug, "new_state": JobStatuses.COMPLETED},
            )
        )
        self.assertFalse(resp.json().get("form_is_valid", False))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)

    def test_no_new_phases_on_a_completed_job(self):
        before = self.job.phases.count()
        resp = self.http.post(
            reverse("phase_create", kwargs={"job_slug": self.job.slug}),
            {"title": "Sneaky"},
        )
        self.assertEqual(resp.status_code, 400)
        clone_url = reverse(
            "phase_clone", kwargs={"job_slug": self.job.slug, "slug": self.delivered.slug}
        )
        resp = self.http.post(clone_url, {"clone_identity": "on"})
        self.assertFalse(resp.json().get("form_is_valid", False))
        self.assertIn("Reopen it to add more phases", resp.json()["html_form"])
        self.assertEqual(self.job.phases.count(), before)


class PhaseReopenTests(CascadeTestBase):
    def setUp(self):
        super().setUp()
        self.http.force_login(self.actor)

    def _reopen(self, phase, reason="Client found an issue"):
        return self.http.post(
            reverse(
                "phase_update_workflow",
                kwargs={
                    "job_slug": self.job.slug,
                    "slug": phase.slug,
                    "new_state": PhaseStatuses.IN_PROGRESS,
                },
            ),
            {"reason": reason},
        )

    def test_reopening_phase_reopens_completed_job(self):
        phase = self._phase(PhaseStatuses.DELIVERED)
        self._set_job_status(JobStatuses.COMPLETED)
        self.assertTrue(self._reopen(phase).json()["form_is_valid"])
        phase.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(phase.status, PhaseStatuses.IN_PROGRESS)
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)
        self.assertIn("Client found an issue", _workflow_events(phase).get().message)
        job_event = _workflow_events(self.job).get()
        self.assertIn(phase.phase_id, job_event.message)
        self.assertIn("Completed to In Progress", job_event.message)

    def test_reopening_completed_phase_on_active_job_leaves_job(self):
        phase = self._phase(PhaseStatuses.COMPLETED)
        self._set_job_status(JobStatuses.IN_PROGRESS)
        self.assertTrue(self._reopen(phase).json()["form_is_valid"])
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)
        self.assertFalse(_workflow_events(self.job).exists())

    def test_reopen_requires_a_reason(self):
        phase = self._phase(PhaseStatuses.DELIVERED)
        self.assertFalse(self._reopen(phase, reason="").json().get("form_is_valid", False))
        phase.refresh_from_db()
        self.assertEqual(phase.status, PhaseStatuses.DELIVERED)

    def test_cannot_reopen_on_archived_job(self):
        phase = self._phase(PhaseStatuses.DELIVERED)
        self._set_job_status(JobStatuses.ARCHIVED)
        self.assertFalse(phase.can_proceed_to_reopen())

    def test_completion_is_logged_as_completed(self):
        phase = self._phase(PhaseStatuses.IN_PROGRESS)
        self._set_job_status(JobStatuses.IN_PROGRESS)
        phase.to_completed(self.actor)
        phase.save()
        self.assertTrue(
            AuditEvent.objects.filter(
                target_id=str(phase.pk),
                message__endswith=PhaseStatuses.CHOICES[PhaseStatuses.COMPLETED][1],
            ).exists()
        )


class CompletedJobSafetyNetTests(CascadeTestBase):
    """An unfinished phase must never sit hidden on a Completed job."""

    def test_active_phase_on_completed_job_reopens_to_in_progress(self):
        phase = self._phase(PhaseStatuses.DELIVERED)
        self._set_job_status(JobStatuses.COMPLETED)
        Phase.objects.filter(pk=phase.pk).update(status=PhaseStatuses.PENDING_TQA)
        phase.refresh_from_db()
        phase.save()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)
        self.assertIn("automatic", _workflow_events(self.job).get().message)

    def test_draft_phases_dont_reopen_completed_job(self):
        # Old completed jobs carry many never-started drafts; they aren't on any
        # queue, so saving one mustn't churn the job.
        self._set_job_status(JobStatuses.COMPLETED)
        self._phase(PhaseStatuses.DRAFT).save()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.COMPLETED)

    def test_finished_phases_leave_completed_job_alone(self):
        phase = self._phase(PhaseStatuses.DELIVERED)
        self._set_job_status(JobStatuses.COMPLETED)
        phase.save()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.COMPLETED)


class BookingRuleTests(CascadeTestBase):
    def setUp(self):
        super().setUp()
        self._set_job_status(JobStatuses.IN_PROGRESS)
        self.http.force_login(self.actor)

    def test_block_reasons(self):
        self.assertIsNone(self._phase(PhaseStatuses.PENDING_SCHED).booking_block_reason())
        self.assertIsNone(self._phase(PhaseStatuses.QA_TECH).booking_block_reason())
        self.assertIn("Draft", self._phase(PhaseStatuses.DRAFT).booking_block_reason())
        self.assertIn(
            "Reopen the phase", self._phase(PhaseStatuses.DELIVERED).booking_block_reason()
        )
        phase = self._phase(PhaseStatuses.IN_PROGRESS)
        self._set_job_status(JobStatuses.COMPLETED)
        phase.refresh_from_db()
        self.assertIn("Reopen the job", phase.booking_block_reason())

    def test_system_writes_of_history_still_work(self):
        # Imports / demo data book historical work straight through the model.
        self._slot(self._phase(PhaseStatuses.DELIVERED))
        self._slot(self._phase(PhaseStatuses.DRAFT))

    def _locked_slot(self):
        phase = self._phase(PhaseStatuses.IN_PROGRESS)
        slot = self._slot(phase, days_ahead=1)
        Phase.objects.filter(pk=phase.pk).update(status=PhaseStatuses.DELIVERED)
        return phase, slot

    def test_drag_refused_on_locked_phase(self):
        _, slot = self._locked_slot()
        new_start = timezone.localtime(slot.start + timedelta(days=1))
        resp = self.http.post(
            reverse("change_scheduler_slot_date", kwargs={"pk": slot.pk}),
            {
                "user": self.actor.pk,
                "start": new_start.strftime("%Y-%m-%d %H:%M"),
                "end": (new_start + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"),
            },
        )
        body = resp.json()
        self.assertFalse(body["form_is_valid"])
        self.assertIn("Reopen the phase", body["error"])
        old_start = slot.start
        slot.refresh_from_db()
        self.assertEqual(slot.start, old_start)

    def test_feed_marks_locked_slots(self):
        _, slot = self._locked_slot()
        slot.refresh_from_db()
        data = slot.get_schedule_json()
        self.assertFalse(data["can_edit"])
        self.assertIn("Reopen the phase", data["locked_reason"])
        active = self._slot(self._phase(PhaseStatuses.IN_PROGRESS), days_ahead=3)
        self.assertNotIn("locked_reason", active.get_schedule_json())

    def test_job_shift_skips_locked_phases(self):
        _, locked = self._locked_slot()
        open_slot = self._slot(self._phase(PhaseStatuses.IN_PROGRESS), days_ahead=2)
        locked_start, open_start = locked.start, open_slot.start
        resp = self.http.post(
            reverse("job_schedule_shift", kwargs={"slug": self.job.slug}),
            {"direction": "forward", "days": 7},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        locked.refresh_from_db()
        open_slot.refresh_from_db()
        self.assertEqual(locked.start, locked_start)
        self.assertEqual(open_slot.start, open_start + timedelta(days=7))

    def test_shift_refused_on_completed_job(self):
        slot = self._slot(self._phase(PhaseStatuses.DELIVERED))
        self._set_job_status(JobStatuses.COMPLETED)
        start = slot.start
        resp = self.http.post(
            reverse("job_schedule_shift", kwargs={"slug": self.job.slug}),
            {"direction": "forward", "days": 7},
        )
        self.assertFalse(resp.json()["form_is_valid"])
        self.assertIn("Reopen the job", resp.json()["html_form"])
        slot.refresh_from_db()
        self.assertEqual(slot.start, start)

    def test_undo_refused_once_phase_is_locked(self):
        phase = self._phase(PhaseStatuses.IN_PROGRESS)
        slot = self._slot(phase, days_ahead=1)
        before = schedule_history.snapshot(slot)
        slot.end = slot.end - timedelta(hours=1)
        slot.save()
        action = schedule_history.record(
            self.actor, ScheduleActionType.UPDATE, [before], [schedule_history.snapshot(slot)]
        )
        Phase.objects.filter(pk=phase.pk).update(status=PhaseStatuses.DELIVERED)
        with self.assertRaises(ValidationError):
            schedule_history.revert(action, self.actor)
        self.assertEqual(TimeSlot.objects.get(pk=slot.pk).end, slot.end)
