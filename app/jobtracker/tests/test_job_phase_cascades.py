from datetime import timedelta
from unittest import mock
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import User
from jobtracker.models import (
    Client,
    Job,
    Phase,
    OrganisationalUnit,
    TimeSlot,
    TimeSlotType,
)
from jobtracker.enums import (
    DefaultTimeSlotTypes,
    JobStatuses,
    PhaseStatuses,
    TimeSlotDeliveryRole,
)


class CascadeTestBase(TestCase):
    """Shared fixtures for the job/phase cascade regression tests.

    The first user created is promoted to superuser by User.save(), so
    ``self.actor`` is an admin and passes every permission check.
    """

    def setUp(self):
        super().setUp()
        self.actor = User.objects.create_user(email="actor@test.com", password="pw12345")
        self.unit = OrganisationalUnit.objects.create(name="Test Unit")
        self.client_obj = Client.objects.create(name="Test Client")
        self.job = Job.objects.create(
            unit=self.unit,
            client=self.client_obj,
            title="Test Job",
            created_by=self.actor,
            account_manager=self.actor,
        )
        self.delivery_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
        self.http = TestClient(HTTP_HOST="localhost")

    def _phase(self, status=PhaseStatuses.PENDING_SCHED, job=None, **kwargs):
        return Phase.objects.create(
            job=job or self.job, title="P", status=status, **kwargs
        )

    def _slot(self, phase, days_ahead=0):
        start = (timezone.now() + timedelta(days=days_ahead)).replace(microsecond=0)
        return TimeSlot.objects.create(
            user=self.actor,
            slot_type=self.delivery_type,
            phase=phase,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=start,
            end=start + timedelta(hours=8),
        )

    def _set_job_status(self, status):
        Job.objects.filter(pk=self.job.pk).update(status=status)
        self.job.refresh_from_db()


class JobLostCascadeTests(CascadeTestBase):
    """T-01: marking a job Lost must persist the cancellation of its phases."""

    def test_lost_via_view_persists_phase_cancellation(self):
        self._set_job_status(JobStatuses.PENDING_START)
        live = self._phase(PhaseStatuses.SCHEDULED_CONFIRMED)
        self._slot(live)
        pending = self._phase(PhaseStatuses.PENDING_SCHED)
        delivered = self._phase(PhaseStatuses.DELIVERED)
        deleted = self._phase(PhaseStatuses.DELETED)

        self.http.force_login(self.actor)
        resp = self.http.post(
            reverse(
                "job_update_workflow",
                kwargs={"slug": self.job.slug, "new_state": JobStatuses.LOST},
            )
        )
        self.assertEqual(resp.status_code, 200)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.LOST)
        for phase in (live, pending):
            phase.refresh_from_db()
            self.assertEqual(phase.status, PhaseStatuses.CANCELLED)
        self.assertEqual(live.timeslots.count(), 0)
        # Finished / already-closed phases are left as they were.
        delivered.refresh_from_db()
        deleted.refresh_from_db()
        self.assertEqual(delivered.status, PhaseStatuses.DELIVERED)
        self.assertEqual(deleted.status, PhaseStatuses.DELETED)


class JobDeleteWithDeletedPhaseTests(CascadeTestBase):
    """C1: an already-deleted phase must not block deleting its job."""

    def test_job_with_deleted_phase_is_deletable(self):
        self._phase(PhaseStatuses.DELETED)
        live = self._phase(PhaseStatuses.PENDING_SCHED)

        self.assertTrue(self.job.can_to_delete())
        self.job.to_delete(self.actor)
        self.job.save()

        self.job.refresh_from_db()
        live.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.DELETED)
        self.assertEqual(live.status, PhaseStatuses.DELETED)


class PhaseBulkDeleteTests(CascadeTestBase):
    """C2: the bulk "Deleted" workflow modal used a non-existent method."""

    def test_bulk_deleted_modal_returns_200(self):
        phase = self._phase(PhaseStatuses.PENDING_SCHED)
        self.http.force_login(self.actor)
        resp = self.http.get(
            reverse(
                "phases_bulk_workflow_modal",
                kwargs={"job_slug": self.job.slug, "new_state": PhaseStatuses.DELETED},
            )
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(phase.title, resp.json()["html_form"])


class AutoCompleteCronTests(CascadeTestBase):
    """C3: the auto-complete cron must complete each job exactly once."""

    def test_job_completed_once_with_many_delivered_phases(self):
        from jobtracker.tasks import task_progress_workflows

        self._set_job_status(JobStatuses.IN_PROGRESS)
        for _ in range(3):
            self._phase(PhaseStatuses.DELIVERED)

        with mock.patch.object(Job, "fire_status_notification") as fired:
            task_progress_workflows().do()

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.COMPLETED)
        completed_calls = [
            c for c in fired.call_args_list if c.args == (JobStatuses.COMPLETED,)
        ]
        self.assertEqual(len(completed_calls), 1)


class AllPhasesFinishedTests(CascadeTestBase):
    """C4: delivering a phase and the cron agree on "all phases finished"."""

    def setUp(self):
        super().setUp()
        self._set_job_status(JobStatuses.IN_PROGRESS)

    def _deliver(self, phase):
        phase.to_delivered(self.actor)
        phase.save()
        self.job.refresh_from_db()

    def test_postponed_phase_blocks_completion_on_delivery(self):
        phase = self._phase(PhaseStatuses.COMPLETED)
        self._phase(PhaseStatuses.POSTPONED)
        self._deliver(phase)
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)

    def test_postponed_phase_blocks_completion_in_cron(self):
        from jobtracker.tasks import task_progress_workflows

        self._phase(PhaseStatuses.DELIVERED)
        self._phase(PhaseStatuses.POSTPONED)
        task_progress_workflows().do()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)

    def test_cancelled_phase_counts_as_finished(self):
        phase = self._phase(PhaseStatuses.COMPLETED)
        self._phase(PhaseStatuses.CANCELLED)
        self._deliver(phase)
        self.assertEqual(self.job.status, JobStatuses.COMPLETED)


class ScopedClearTests(CascadeTestBase):
    """C5: a phase-scoped scheduler clear must revert the emptied phase."""

    def test_scoped_clear_reverts_phase_to_pending(self):
        from urllib.parse import urlencode

        phase = self._phase(PhaseStatuses.SCHEDULED_CONFIRMED)
        slot = self._slot(phase)
        day = timezone.localtime(slot.start).date().isoformat()
        query = urlencode(
            {
                "start": day + "T00:00:00",
                "end": day + "T23:59:59",
                "resource_id": self.actor.pk,
                "phase": phase.pk,
            }
        )
        self.http.force_login(self.actor)
        resp = self.http.post(
            reverse("clear_scheduler_range") + "?" + query,
            {"user_action": "approve_action"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["form_is_valid"])

        phase.refresh_from_db()
        self.assertEqual(phase.timeslots.count(), 0)
        self.assertEqual(phase.status, PhaseStatuses.PENDING_SCHED)


class DeletedEntitySubscriptionTests(CascadeTestBase):
    """C6: saving a deleted job/phase must not re-run auto-subscription."""

    def test_deleted_job_and_phase_are_not_resubscribed(self):
        self._phase(PhaseStatuses.PENDING_SCHED)
        with mock.patch("notifications.signals.auto_subscribe_users") as subscribe:
            self.job.save()
            self.assertTrue(subscribe.called)  # sanity: live saves subscribe
            subscribe.reset_mock()

            self.job.to_delete(self.actor)
            self.job.save()
        subscribe.assert_not_called()


class StoredDatesCronTests(CascadeTestBase):
    """C7: the nightly dates cron must persist (and clear) stored dates."""

    def _run_cron(self):
        from chaotica_utils.tasks import task_update_phase_dates

        task_update_phase_dates().do()

    def test_cron_persists_dates_from_slots(self):
        phase = self._phase(PhaseStatuses.SCHEDULED_CONFIRMED)
        slot = self._slot(phase, days_ahead=3)
        Phase.objects.filter(pk=phase.pk).update(_start_date=None, _delivery_date=None)

        self._run_cron()

        phase.refresh_from_db()
        self.assertEqual(phase._start_date, slot.start.date())
        self.assertIsNotNone(phase._delivery_date)

    def test_cron_clears_dates_when_no_slots(self):
        phase = self._phase(PhaseStatuses.PENDING_SCHED)
        stale = timezone.now().date()
        Phase.objects.filter(pk=phase.pk).update(
            _start_date=stale, _delivery_date=stale
        )

        self._run_cron()

        phase.refresh_from_db()
        self.assertIsNone(phase._start_date)
        self.assertIsNone(phase._delivery_date)


class PhaseRevivalGuardTests(CascadeTestBase):
    """G1: closed phases can't be revived; closed jobs' phases can't progress."""

    def test_cancelled_phase_cannot_be_postponed(self):
        phase = self._phase(PhaseStatuses.CANCELLED)
        self.assertFalse(phase.can_to_postponed())
        self.assertFalse(phase.can_to_cancelled())

    def test_closed_phases_cannot_be_postponed(self):
        for status in (PhaseStatuses.DELETED, PhaseStatuses.ARCHIVED):
            self.assertFalse(self._phase(status).can_proceed_to_postponed())

    def test_live_phase_can_still_be_postponed(self):
        self.assertTrue(self._phase(PhaseStatuses.IN_PROGRESS).can_proceed_to_postponed())

    def test_phase_on_lost_job_cannot_progress(self):
        phase = self._phase(PhaseStatuses.POSTPONED)
        ready = self._phase(PhaseStatuses.READY_TO_BEGIN)
        self._set_job_status(JobStatuses.LOST)
        phase.refresh_from_db()
        ready.refresh_from_db()
        self.assertFalse(phase.can_to_pending_sched())
        self.assertFalse(ready.can_proceed_to_in_progress())

    def test_phase_on_completed_job_can_still_progress(self):
        phase = self._phase(PhaseStatuses.COMPLETED)
        self._set_job_status(JobStatuses.COMPLETED)
        phase.refresh_from_db()
        self.assertTrue(phase.can_proceed_to_delivered())

    def test_cron_skips_lost_jobs(self):
        from jobtracker.tasks import task_progress_workflows

        ready = self._phase(
            PhaseStatuses.READY_TO_BEGIN,
            desired_start_date=timezone.now().date() - timedelta(days=1),
        )
        self._set_job_status(JobStatuses.LOST)
        with mock.patch.object(Phase, "to_in_progress") as started:
            task_progress_workflows().do()
        started.assert_not_called()
        ready.refresh_from_db()
        self.assertEqual(ready.status, PhaseStatuses.READY_TO_BEGIN)
