"""Stale alarm group (jobtracker.alarms) and the causes it guards against:
jobs stranded in Scoping Complete, all-cancelled jobs counted as Completed, and
late reminders for stalled work repeating forever."""

from datetime import timedelta
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from jobtracker.alarms import build_alarms
from jobtracker.enums import JobStatuses, PhaseStatuses
from jobtracker.models import Job, Phase

from .test_job_phase_cascades import CascadeTestBase


class StaleAlarmTests(CascadeTestBase):
    def setUp(self):
        super().setUp()
        self._set_job_status(JobStatuses.IN_PROGRESS)
        self.long_ago = timezone.now() - timedelta(days=60)

    def _age(self, obj, when=None):
        type(obj).objects.filter(pk=obj.pk).update(status_changed_date=when or self.long_ago)

    def _alarms(self):
        return build_alarms(self.actor)  # superuser: manager scope everywhere

    def test_stalled_phase_moves_from_overdue_to_stale(self):
        phase = self._phase(
            PhaseStatuses.PRE_CHECKS,
            desired_delivery_date=(timezone.now() - timedelta(days=50)).date(),
        )
        self._slot(phase, days_ahead=-45)
        self._age(phase)
        alarms = self._alarms()
        self.assertIn(phase, alarms["stale_stalled"])
        self.assertNotIn(phase, alarms["delivery_overdue"])
        self.assertIsNotNone(alarms["stale_stalled"].get(pk=phase.pk).last_booking)

    def test_phase_with_upcoming_booking_is_not_stalled(self):
        phase = self._phase(PhaseStatuses.IN_PROGRESS)
        self._slot(phase, days_ahead=3)
        self._age(phase)
        self.assertNotIn(phase, self._alarms()["stale_stalled"])

    def test_qa_phases_stay_overdue_not_stale(self):
        # Waiting on a reviewer with no bookings is normal for QA.
        phase = self._phase(
            PhaseStatuses.PENDING_PQA,
            due_to_presqa_set=(timezone.now() - timedelta(days=50)).date(),
        )
        self._age(phase)
        alarms = self._alarms()
        self.assertNotIn(phase, alarms["stale_stalled"])
        self.assertIn(phase, alarms["pqa_overdue"])

    def test_never_booked_demand(self):
        phase = self._phase(
            PhaseStatuses.PENDING_SCHED,
            desired_delivery_date=(timezone.now() - timedelta(days=60)).date(),
        )
        alarms = self._alarms()
        self.assertIn(phase, alarms["stale_unbooked"])
        self.assertNotIn(phase, alarms["delivery_overdue"])

    def test_long_postponed(self):
        phase = self._phase(PhaseStatuses.POSTPONED)
        self._age(phase, timezone.now() - timedelta(days=120))
        self.assertIn(phase, self._alarms()["stale_postponed"])

    def test_job_with_only_cancelled_phases(self):
        self._set_job_status(JobStatuses.SCOPING_COMPLETE)
        self._phase(PhaseStatuses.CANCELLED)
        Job.objects.filter(pk=self.job.pk).update(
            desired_delivery_date=(timezone.now() - timedelta(days=10)).date()
        )
        alarms = self._alarms()
        self.assertIn(self.job, alarms["stale_no_live_phases"])
        self.assertNotIn(self.job, alarms["job_overdue"])

    def test_dormant_job(self):
        self._set_job_status(JobStatuses.DRAFT)
        self._age(self.job, timezone.now() - timedelta(days=200))
        self.assertIn(self.job, self._alarms()["stale_dormant_jobs"])

    def test_dashboard_shows_stale_group_separately(self):
        self._phase(PhaseStatuses.POSTPONED).save()
        Phase.objects.filter(status=PhaseStatuses.POSTPONED).update(
            status_changed_date=timezone.now() - timedelta(days=120)
        )
        self.http.force_login(self.actor)
        resp = self.http.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["stale_alarm_count"], 1)
        # The red badge is overdue-only.
        self.assertEqual(resp.context["alarm_count"], 0)
        # Nothing overdue, so Alarms isn't the first tab: it loads on demand.
        tab = self.http.get(reverse("dashboard_tab", args=["alarms"]))
        self.assertContains(tab, "Long postponed")

    def test_entropy_counts_stale(self):
        from chaotica_utils.views.entropy import compute_entropy

        phase = self._phase(PhaseStatuses.POSTPONED)
        self._age(phase, timezone.now() - timedelta(days=120))
        keys = {f["key"] for f in compute_entropy(self.actor)["factors"]}
        self.assertIn("stale_postponed", keys)


class StaleCauseTests(CascadeTestBase):
    def test_starting_a_phase_lifts_scoping_complete_job(self):
        self._set_job_status(JobStatuses.SCOPING_COMPLETE)
        phase = self._phase(PhaseStatuses.READY_TO_BEGIN)
        phase.to_in_progress(self.actor)
        phase.save()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)

    def test_all_cancelled_job_is_not_completed(self):
        from jobtracker.tasks import task_progress_workflows

        self._set_job_status(JobStatuses.IN_PROGRESS)
        self._phase(PhaseStatuses.CANCELLED)
        self.assertTrue(self.job.all_phases_finished())
        self.assertFalse(self.job.can_to_complete())
        task_progress_workflows().do()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatuses.IN_PROGRESS)

    def test_delivered_plus_cancelled_still_completes(self):
        self._set_job_status(JobStatuses.IN_PROGRESS)
        self._phase(PhaseStatuses.DELIVERED)
        self._phase(PhaseStatuses.CANCELLED)
        self.assertTrue(self.job.can_to_complete())

    def test_no_late_reminders_for_stalled_phases(self):
        from jobtracker.tasks import task_fire_job_notifications

        self._set_job_status(JobStatuses.IN_PROGRESS)
        stalled = self._phase(PhaseStatuses.PRE_CHECKS)
        Phase.objects.filter(pk=stalled.pk).update(
            status_changed_date=timezone.now() - timedelta(days=60)
        )
        live = self._phase(PhaseStatuses.PRE_CHECKS)
        self._slot(live, days_ahead=2)
        seen = []
        with mock.patch.object(
            Phase, "fire_late_prechecks_notification",
            autospec=True, side_effect=lambda p: seen.append(p.pk),
        ), mock.patch.object(
            Phase, "is_prechecks_late", new_callable=mock.PropertyMock, return_value=True
        ):
            task_fire_job_notifications().do()
        self.assertIn(live.pk, seen)
        self.assertNotIn(stalled.pk, seen)
