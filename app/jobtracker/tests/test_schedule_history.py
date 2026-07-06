from datetime import timedelta
from django.test import TestCase
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.contrib.auth.models import Permission

from chaotica_utils.models import User
from jobtracker.models import (
    Client,
    Job,
    Phase,
    OrganisationalUnit,
    TimeSlot,
    TimeSlotType,
    TimeSlotComment,
    ScheduleAction,
    ScheduleActionType,
)
from jobtracker.enums import DefaultTimeSlotTypes, PhaseStatuses, TimeSlotDeliveryRole
from jobtracker import schedule_history


class ScheduleHistoryBase(TestCase):
    def setUp(self):
        super().setUp()
        self.actor = User.objects.create_user(email="actor@test.com", password="pw12345")
        self.other = User.objects.create_user(email="other@test.com", password="pw12345")
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
        self.delivery_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
        self.internal_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.UNASSIGNED)
        self.start = timezone.now().replace(microsecond=0)
        self.end = self.start + timedelta(hours=8)

    def _internal_slot(self, user=None):
        return TimeSlot.objects.create(
            user=user or self.actor,
            slot_type=self.internal_type,
            start=self.start,
            end=self.end,
        )

    def _delivery_slot(self, user=None):
        return TimeSlot.objects.create(
            user=user or self.actor,
            slot_type=self.delivery_type,
            phase=self.phase,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=self.start,
            end=self.end,
        )


class RecordTests(ScheduleHistoryBase):
    def test_record_create(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        self.assertEqual(action.action_type, ScheduleActionType.CREATE)
        self.assertEqual(len(action.payload), 1)
        item = action.payload[0]
        self.assertIsNone(item["before"])
        self.assertIsNotNone(item["after"])
        self.assertEqual(item["model"], "timeslot")
        self.assertEqual(item["pk"], slot.pk)

    def test_record_update(self):
        slot = self._internal_slot()
        before = schedule_history.snapshot(slot)
        slot.end = self.end + timedelta(hours=2)
        slot.save()
        action = schedule_history.record(
            self.actor, ScheduleActionType.UPDATE, [before], [schedule_history.snapshot(slot)]
        )
        item = action.payload[0]
        self.assertIsNotNone(item["before"])
        self.assertIsNotNone(item["after"])
        self.assertNotEqual(item["before"]["end"], item["after"]["end"])

    def test_record_delete(self):
        slot = self._internal_slot()
        before = schedule_history.snapshot(slot)
        slot.delete()
        action = schedule_history.record_deletes(self.actor, [before])
        item = action.payload[0]
        self.assertIsNotNone(item["before"])
        self.assertIsNone(item["after"])

    def test_record_noop_returns_none(self):
        self.assertIsNone(schedule_history.record(self.actor, ScheduleActionType.UPDATE, [], []))

    def test_scope_derivation_delivery(self):
        slot = self._delivery_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        self.assertEqual(action.job_id, self.job.pk)
        self.assertEqual(action.phase_id, self.phase.pk)

    def test_scope_derivation_internal_is_global(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        self.assertIsNone(action.job_id)
        self.assertIsNone(action.phase_id)

    def test_record_comment_create(self):
        comment = TimeSlotComment.objects.create(
            user=self.actor, comment="hello", start=self.start, end=self.end
        )
        action = schedule_history.record_creates(self.actor, [comment])
        self.assertEqual(action.payload[0]["model"], "timeslotcomment")
        self.assertEqual(action.payload[0]["after"]["comment"], "hello")


class RevertTests(ScheduleHistoryBase):
    def test_revert_create_deletes(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        schedule_history.revert(action, self.actor)
        self.assertFalse(TimeSlot.objects.filter(pk=slot.pk).exists())
        action.refresh_from_db()
        self.assertTrue(action.reverted)
        self.assertIsNotNone(action.reverted_by)

    def test_revert_delete_recreates(self):
        slot = self._internal_slot()
        before = schedule_history.snapshot(slot)
        slot.delete()
        action = schedule_history.record_deletes(self.actor, [before])
        schedule_history.revert(action, self.actor)
        # A slot with the same field values should exist again.
        self.assertTrue(
            TimeSlot.objects.filter(user=self.actor, start=self.start, end=self.end).exists()
        )

    def test_revert_update_restores(self):
        slot = self._internal_slot()
        before = schedule_history.snapshot(slot)
        new_end = self.end + timedelta(hours=3)
        slot.end = new_end
        slot.save()
        action = schedule_history.record(
            self.actor, ScheduleActionType.UPDATE, [before], [schedule_history.snapshot(slot)]
        )
        schedule_history.revert(action, self.actor)
        slot.refresh_from_db()
        self.assertEqual(slot.end, self.end)

    def test_revert_is_itself_recorded_and_redoable(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        inverse = schedule_history.revert(action, self.actor)
        self.assertEqual(inverse.action_type, ScheduleActionType.REVERT)
        # Redo: revert the revert → recreate the slot.
        schedule_history.revert(inverse, self.actor)
        self.assertTrue(
            TimeSlot.objects.filter(user=self.actor, start=self.start, end=self.end).exists()
        )

    def test_cannot_revert_twice(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        schedule_history.revert(action, self.actor)
        action.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            schedule_history.revert(action, self.actor)

    def test_other_user_cannot_revert_without_perm(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        self.assertFalse(action.can_revert(self.other))
        with self.assertRaises(PermissionDenied):
            schedule_history.revert(action, self.other)

    def test_user_with_perm_can_revert_any(self):
        slot = self._internal_slot()
        action = schedule_history.record_creates(self.actor, [slot])
        perm = Permission.objects.get(codename="revert_any_scheduleaction")
        self.other.user_permissions.add(perm)
        self.other = User.objects.get(pk=self.other.pk)  # reset perm cache
        self.assertTrue(action.can_revert(self.other))

    def test_revert_delivery_recalcs_phase_status(self):
        # Booking a slot moves the phase to tentative; reverting the create should
        # drop it back to pending scheduling (TimeSlot.delete side effect fires).
        self.phase.status = PhaseStatuses.PENDING_SCHED
        self.phase.save()
        slot = self._delivery_slot()
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, PhaseStatuses.SCHEDULED_TENTATIVE)
        action = schedule_history.record_creates(self.actor, [slot])
        schedule_history.revert(action, self.actor)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, PhaseStatuses.PENDING_SCHED)
