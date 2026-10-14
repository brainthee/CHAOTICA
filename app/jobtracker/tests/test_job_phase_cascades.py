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
