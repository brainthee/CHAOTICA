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
    PhaseStatuses,
    TimeSlotDeliveryRole,
)


class PhaseTeardownTests(TestCase):
    """Terminal phase transitions must free the scheduler and land on their
    real target status (not get bounced to Pending Scheduling by the last-slot
    auto-revert in TimeSlot.delete)."""

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

    def _confirmed_phase_with_slot(self):
        phase = Phase.objects.create(
            job=self.job, title="P", status=PhaseStatuses.SCHEDULED_CONFIRMED
        )
        start = timezone.now().replace(microsecond=0)
        TimeSlot.objects.create(
            user=self.actor,
            slot_type=self.delivery_type,
            phase=phase,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=start,
            end=start + timedelta(hours=8),
        )
        return phase

    def test_postpone_clears_slots_and_lands_postponed(self):
        phase = self._confirmed_phase_with_slot()
        phase.to_postponed(self.actor)
        phase.save()
        phase.refresh_from_db()
        self.assertEqual(phase.status, PhaseStatuses.POSTPONED)
        self.assertEqual(phase.timeslots.count(), 0)

    def test_cancel_clears_slots_and_lands_cancelled(self):
        phase = self._confirmed_phase_with_slot()
        phase.to_cancelled(self.actor)
        phase.save()
        phase.refresh_from_db()
        self.assertEqual(phase.status, PhaseStatuses.CANCELLED)
        self.assertEqual(phase.timeslots.count(), 0)
