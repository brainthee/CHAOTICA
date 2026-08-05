from datetime import timedelta
from django.test import TestCase
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


class JobDeleteCascadeTests(TestCase):
    """Deleting a job must cascade its phases to DELETED and clear timeslots.

    Regression for the soft-delete bug where Job.to_delete() called
    phase.to_deleted() without saving, leaving phases active and still
    generating notification emails.
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
        self.phase = Phase.objects.create(job=self.job, title="Phase 1")
        delivery_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
        start = timezone.now().replace(microsecond=0)
        self.slot = TimeSlot.objects.create(
            user=self.actor,
            slot_type=delivery_type,
            phase=self.phase,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=start,
            end=start + timedelta(hours=8),
        )

    def test_deleting_job_persists_phase_delete_and_clears_timeslots(self):
        self.job.to_delete(self.actor)
        self.job.save()

        self.job.refresh_from_db()
        self.phase.refresh_from_db()

        self.assertEqual(self.job.status, JobStatuses.DELETED)
        # Phase status change must actually be persisted, not just in-memory.
        self.assertEqual(self.phase.status, PhaseStatuses.DELETED)
        # Scheduled timeslots must not linger on the scheduler.
        self.assertEqual(TimeSlot.objects.filter(pk=self.slot.pk).count(), 0)
        self.assertEqual(self.phase.timeslots.count(), 0)
