import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from jobtracker.enums import TimeSlotDeliveryRole, PhaseStatuses
from reporting.utils.query_builder import (
    resolve_relative_date_token, convert_value_to_proper_type,
)
from reporting.resolvers import REPORTING_RESOLVERS, _days_by_role, _assigned_engineers
from reporting.services.data_service import DataService


class RelativeDateTokenTests(SimpleTestCase):
    def test_positive_offset(self):
        self.assertEqual(
            resolve_relative_date_token('today+30d'),
            datetime.date.today() + datetime.timedelta(days=30),
        )

    def test_negative_offset_and_whitespace(self):
        self.assertEqual(
            resolve_relative_date_token(' today - 7 d '),
            datetime.date.today() - datetime.timedelta(days=7),
        )

    def test_non_token_returns_none(self):
        self.assertIsNone(resolve_relative_date_token('nonsense'))
        self.assertIsNone(resolve_relative_date_token('2026-01-01'))

    def test_convert_value_uses_token_for_dates(self):
        self.assertEqual(
            convert_value_to_proper_type('today+1d', 'DateField'),
            datetime.date.today() + datetime.timedelta(days=1),
        )


class _StubTimeSlot:
    def __init__(self, role, hours, user=None):
        self.deliveryRole = role
        self._hours = Decimal(hours)
        self.user = user
        self.user_id = getattr(user, 'id', None)

    def get_business_hours(self):
        return self._hours


class _StubRelation:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class ResolverTests(SimpleTestCase):
    def _phase(self, slots, hours_in_day=8):
        phase = SimpleNamespace()
        phase.timeslots = _StubRelation(slots)
        phase.get_hours_in_day = lambda: Decimal(hours_in_day)
        return phase

    def test_days_by_role_only_counts_matching_role(self):
        slots = [
            _StubTimeSlot(TimeSlotDeliveryRole.DELIVERY, 8),
            _StubTimeSlot(TimeSlotDeliveryRole.DELIVERY, 8),
            _StubTimeSlot(TimeSlotDeliveryRole.REPORTING, 8),
        ]
        phase = self._phase(slots)
        self.assertEqual(_days_by_role(TimeSlotDeliveryRole.DELIVERY)(phase, {}), Decimal('2.00'))
        self.assertEqual(_days_by_role(TimeSlotDeliveryRole.REPORTING)(phase, {}), Decimal('1.00'))

    def test_assigned_engineers_dedupes_and_sorts(self):
        u1 = SimpleNamespace(id=1, get_full_name=lambda: 'Zoe Zheng')
        u2 = SimpleNamespace(id=2, get_full_name=lambda: 'Amy Adams')
        slots = [
            _StubTimeSlot(TimeSlotDeliveryRole.DELIVERY, 8, u1),
            _StubTimeSlot(TimeSlotDeliveryRole.REPORTING, 8, u1),
            _StubTimeSlot(TimeSlotDeliveryRole.DELIVERY, 8, u2),
        ]
        phase = self._phase(slots)
        self.assertEqual(_assigned_engineers(phase, {}), 'Amy Adams, Zoe Zheng')

    def test_status_label_resolver(self):
        phase = SimpleNamespace(status=PhaseStatuses.SCHEDULED_TENTATIVE)
        self.assertEqual(
            REPORTING_RESOLVERS['phase.status_label'].fn(phase, {}),
            dict(PhaseStatuses.CHOICES)[PhaseStatuses.SCHEDULED_TENTATIVE],
        )

    def test_qa_stars_are_stored_rating_plus_one(self):
        # A stored 'Average' (2) reads as 3 stars in the UI; None stays blank.
        for raw, expected in ((0, 1), (2, 3), (4, 5)):
            phase = SimpleNamespace(techqa_report_rating=raw)
            self.assertEqual(
                REPORTING_RESOLVERS['phase.techqa_report_stars'].fn(phase, {}),
                expected,
            )
        blank = SimpleNamespace(techqa_report_rating=None)
        self.assertIsNone(
            REPORTING_RESOLVERS['phase.techqa_report_stars'].fn(blank, {})
        )

    def test_qa_rating_label_resolver(self):
        from jobtracker.enums import TechQARatings
        phase = SimpleNamespace(techqa_report_rating=TechQARatings.AVERAGE)
        self.assertEqual(
            REPORTING_RESOLVERS['phase.techqa_report_rating_label'].fn(phase, {}),
            dict(TechQARatings.CHOICES)[TechQARatings.AVERAGE],
        )

    def test_feedback_text_and_count_by_type(self):
        from jobtracker.enums import FeedbackType
        feedback = [
            SimpleNamespace(feedbackType=FeedbackType.TECH, body='<b>Tidy up</b> the exec summary'),
            SimpleNamespace(feedbackType=FeedbackType.TECH, body='Fix the risk ratings'),
            SimpleNamespace(feedbackType=FeedbackType.PRES, body='Header wrong'),
        ]
        phase = SimpleNamespace(feedback=_StubRelation(feedback))
        self.assertEqual(REPORTING_RESOLVERS['phase.feedback_tech_count'].fn(phase, {}), 2)
        self.assertEqual(REPORTING_RESOLVERS['phase.feedback_pres_count'].fn(phase, {}), 1)
        self.assertEqual(REPORTING_RESOLVERS['phase.feedback_scope_count'].fn(phase, {}), 0)
        # HTML is stripped and bodies joined.
        tech_text = REPORTING_RESOLVERS['phase.feedback_tech_text'].fn(phase, {})
        self.assertIn('Tidy up the exec summary', tech_text)
        self.assertIn('Fix the risk ratings', tech_text)
        self.assertNotIn('<b>', tech_text)
        self.assertEqual(REPORTING_RESOLVERS['phase.feedback_scope_text'].fn(phase, {}), '')

    def test_job_status_label_and_m2m_resolvers(self):
        from jobtracker.enums import JobStatuses
        job = SimpleNamespace(
            status=JobStatuses.PENDING_START,
            charge_codes=_StubRelation([SimpleNamespace(code='ABC-1'), SimpleNamespace(code='ABC-2')]),
            indicative_services=_StubRelation([SimpleNamespace(name='Web App')]),
            scoped_by=_StubRelation([
                SimpleNamespace(id=1, get_full_name=lambda: 'Zoe Zheng'),
                SimpleNamespace(id=2, get_full_name=lambda: 'Amy Adams'),
            ]),
        )
        self.assertEqual(
            REPORTING_RESOLVERS['job.status_label'].fn(job, {}),
            dict(JobStatuses.CHOICES)[JobStatuses.PENDING_START],
        )
        self.assertEqual(REPORTING_RESOLVERS['job.charge_codes'].fn(job, {}), 'ABC-1, ABC-2')
        self.assertEqual(REPORTING_RESOLVERS['job.indicative_services'].fn(job, {}), 'Web App')
        self.assertEqual(REPORTING_RESOLVERS['job.scoped_by'].fn(job, {}), 'Amy Adams, Zoe Zheng')


class DataServiceHelperTests(SimpleTestCase):
    def test_walk_path_traverses_and_tolerates_none(self):
        obj = SimpleNamespace(job=SimpleNamespace(client=SimpleNamespace(name='Acme')))
        self.assertEqual(DataService._walk_path(obj, 'job__client__name'), 'Acme')
        broken = SimpleNamespace(job=None)
        self.assertIsNone(DataService._walk_path(broken, 'job__client__name'))

    def test_field_visible_redacts_sensitive_without_permission(self):
        user = SimpleNamespace(is_superuser=False, has_perm=lambda p: False)
        sensitive = SimpleNamespace(is_sensitive=True, requires_permission='jobtracker.view_secret')
        plain = SimpleNamespace(is_sensitive=False, requires_permission=None)
        self.assertFalse(DataService._field_visible(sensitive, user))
        self.assertTrue(DataService._field_visible(plain, user))

    def test_field_visible_allows_superuser(self):
        superuser = SimpleNamespace(is_superuser=True, has_perm=lambda p: False)
        sensitive = SimpleNamespace(is_sensitive=True, requires_permission='jobtracker.view_secret')
        self.assertTrue(DataService._field_visible(sensitive, superuser))


class ScheduledReportLogicTests(SimpleTestCase):
    """Exercise the pure scheduling/grouping logic without touching the DB."""

    def _sched(self, **kwargs):
        from reporting.models import ScheduledReport
        defaults = dict(
            enabled=True,
            frequency=ScheduledReport.FREQ_WEEKLY,
            day_of_week=2,  # Wednesday
            run_time=datetime.time(9, 0),
            last_sent_at=None,
        )
        defaults.update(kwargs)
        return ScheduledReport(**defaults)

    def _now(self, weekday_date, hour, minute=0):
        from django.utils import timezone
        return timezone.make_aware(datetime.datetime.combine(
            weekday_date, datetime.time(hour, minute)
        ))

    WED = datetime.date(2026, 7, 1)   # a Wednesday
    THU = datetime.date(2026, 7, 2)   # a Thursday

    def test_due_on_correct_weekday_after_time(self):
        self.assertTrue(self._sched().is_due(self._now(self.WED, 10)))

    def test_not_due_before_run_time(self):
        self.assertFalse(self._sched().is_due(self._now(self.WED, 8)))

    def test_not_due_on_wrong_weekday(self):
        self.assertFalse(self._sched(day_of_week=0).is_due(self._now(self.WED, 10)))

    def test_not_due_when_disabled(self):
        self.assertFalse(self._sched(enabled=False).is_due(self._now(self.WED, 10)))

    def test_not_due_if_already_sent_today(self):
        sent = self._now(self.WED, 8)
        self.assertFalse(self._sched(last_sent_at=sent).is_due(self._now(self.WED, 10)))

    def test_daily_ignores_weekday(self):
        from reporting.models import ScheduledReport
        daily = self._sched(frequency=ScheduledReport.FREQ_DAILY, day_of_week=None)
        self.assertTrue(daily.is_due(self._now(self.THU, 10)))

    def test_recipient_list_parses_and_dedupes(self):
        sched = self._sched(recipient_emails='a@x.com, b@x.com\nA@x.com')
        self.assertEqual(sched.recipient_list(), ['a@x.com', 'b@x.com'])

    def test_group_rows_groups_and_drops_empty(self):
        from reporting.models import DataField
        sched = self._sched()
        # Unsaved DataField with an id is a valid FK value and sets split_by_field_id.
        sched.split_by_field = DataField(id=1, field_path='mgr')
        data = [
            {'mgr': 'x@x.com', 'v': 1},
            {'mgr': 'x@x.com', 'v': 2},
            {'mgr': 'y@x.com', 'v': 3},
            {'mgr': None, 'v': 4},
        ]
        groups = sched.group_rows(data)
        self.assertEqual(set(groups.keys()), {'x@x.com', 'y@x.com'})
        self.assertEqual(len(groups['x@x.com']), 2)


from django.test import TestCase
from guardian.shortcuts import assign_perm


class ReportingScopingTests(TestCase):
    """F5: the reporting data queryset must be scoped to the running user's units
    (guardian ``can_view_jobs``), not org-wide, with restricted jobs excluded for
    everyone but superusers."""

    def setUp(self):
        from chaotica_utils.models import User
        from jobtracker.models import Client, Job, OrganisationalUnit

        # create_user makes the first user a superuser; make/keep an explicit one.
        self.superuser = User.objects.create_user(email="su@test.com", password="pw12345")
        self.superuser.is_superuser = True
        self.superuser.save()

        self.unit_a = OrganisationalUnit.objects.create(name="Unit A")
        self.unit_b = OrganisationalUnit.objects.create(name="Unit B")
        self.client_obj = Client.objects.create(name="C")
        common = dict(
            client=self.client_obj, created_by=self.superuser,
            account_manager=self.superuser,
        )
        self.job_a = Job.objects.create(unit=self.unit_a, title="A", **common)
        self.job_b = Job.objects.create(unit=self.unit_b, title="B", **common)
        self.job_a_restricted = Job.objects.create(
            unit=self.unit_a, title="A-restricted", is_restricted=True, **common,
        )

        self.scoped_user = User.objects.create_user(email="scoped@test.com", password="pw12345")
        assign_perm("jobtracker.can_view_jobs", self.scoped_user, self.unit_a)
        self.scoped_user = User.objects.get(pk=self.scoped_user.pk)

        self.nobody = User.objects.create_user(email="nobody@test.com", password="pw12345")

    def _filter(self, user):
        from jobtracker.models import Job
        return set(
            DataService._apply_permission_filter(Job.objects.all(), None, user)
            .values_list("pk", flat=True)
        )

    def test_superuser_sees_all_including_restricted(self):
        pks = self._filter(self.superuser)
        self.assertIn(self.job_b.pk, pks)
        self.assertIn(self.job_a_restricted.pk, pks)

    def test_scoped_user_sees_only_own_unit_non_restricted(self):
        pks = self._filter(self.scoped_user)
        self.assertIn(self.job_a.pk, pks)
        self.assertNotIn(self.job_b.pk, pks)            # other unit excluded
        self.assertNotIn(self.job_a_restricted.pk, pks)  # restricted excluded

    def test_user_without_perms_sees_nothing(self):
        self.assertEqual(self._filter(self.nobody), set())

    def test_can_run_all_reports_is_cross_org_but_excludes_restricted(self):
        assign_perm("reporting.can_run_all_reports", self.nobody)
        user = type(self.nobody).objects.get(pk=self.nobody.pk)
        pks = self._filter(user)
        self.assertIn(self.job_a.pk, pks)
        self.assertIn(self.job_b.pk, pks)
        self.assertNotIn(self.job_a_restricted.pk, pks)


class RunAsUserFormTests(TestCase):
    """F3: a scheduled report may not run as a superuser (privilege escalation)."""

    def setUp(self):
        from chaotica_utils.models import User
        self.superuser = User.objects.create_user(email="su2@test.com", password="pw12345")
        self.normal = User.objects.create_user(email="normal@test.com", password="pw12345")

    def test_run_as_user_queryset_excludes_superusers(self):
        from reporting.forms import ScheduledReportForm
        form = ScheduledReportForm()
        qs = form.fields['run_as_user'].queryset
        self.assertIn(self.normal, qs)
        self.assertNotIn(self.superuser, qs)

    def test_run_as_user_rejects_superuser_on_clean(self):
        from reporting.forms import ScheduledReportForm
        form = ScheduledReportForm(data={'run_as_user': self.superuser.pk})
        self.assertFalse(form.is_valid())
        self.assertIn('run_as_user', form.errors)


from unittest import mock
import os


def _make_report(owner):
    """Minimal Report (+ its required DataArea) for background-run tests."""
    from django.contrib.contenttypes.models import ContentType
    from jobtracker.models import Job
    from reporting.models import DataArea, Report
    area = DataArea.objects.create(
        name="Jobs (test)", content_type=ContentType.objects.get_for_model(Job),
        model_name="Job",
    )
    return Report.objects.create(name="Test report", owner=owner, data_area=area)


class ReportRunProcessingTests(TestCase):
    """The background cron executes a queued run and persists its output."""

    def setUp(self):
        from chaotica_utils.models import User
        self.user = User.objects.create_user(email="runproc@test.com", password="pw12345")
        self.report = _make_report(self.user)

    def _addCleanupFiles(self, run):
        run.refresh_from_db()
        for path in (run.result_path, run.export_path):
            if path:
                self.addCleanup(lambda p=path: os.path.exists(p) and os.remove(p))

    def test_html_run_marks_complete_and_persists_rows(self):
        from reporting.models import ReportRun
        from reporting.tasks import ProcessReportRuns
        run = ReportRun.objects.create(report=self.report, user=self.user)
        rows = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
        with mock.patch("reporting.tasks.DataService.get_report_data", return_value=rows):
            ProcessReportRuns().process_run(run)
        self._addCleanupFiles(run)
        run.refresh_from_db()
        self.assertEqual(run.status, ReportRun.STATUS_COMPLETE)
        self.assertEqual(run.row_count, 2)
        self.assertTrue(run.result_path and os.path.exists(run.result_path))
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.last_run_at)

    def test_export_run_writes_download_file(self):
        from django.http import HttpResponse
        from reporting.models import ReportRun
        from reporting.tasks import ProcessReportRuns
        run = ReportRun.objects.create(report=self.report, user=self.user, export_format="csv")
        fake = HttpResponse(b"id,title\n1,A\n", content_type="text/csv")
        fake["Content-Disposition"] = 'attachment; filename="test.csv"'
        with mock.patch("reporting.tasks.DataService.get_report_data", return_value=[{"id": 1}]), \
             mock.patch("reporting.tasks.ExportService.export_report", return_value=fake):
            ProcessReportRuns().process_run(run)
        self._addCleanupFiles(run)
        run.refresh_from_db()
        self.assertEqual(run.status, ReportRun.STATUS_COMPLETE)
        self.assertTrue(run.export_path and os.path.exists(run.export_path))
        self.assertEqual(run.export_content_type, "text/csv")
        self.assertEqual(run.export_filename, "test.csv")

    def test_failure_is_recorded(self):
        from reporting.models import ReportRun
        from reporting.tasks import ProcessReportRuns
        run = ReportRun.objects.create(report=self.report, user=self.user)
        with mock.patch("reporting.tasks.DataService.get_report_data", side_effect=ValueError("boom")):
            ProcessReportRuns().process_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, ReportRun.STATUS_FAILED)
        self.assertIn("boom", run.error_message)


class ReportRunStatusEndpointTests(TestCase):
    """The polled status endpoint returns the right JSON for each run state."""

    def setUp(self):
        from chaotica_utils.models import User
        self.user = User.objects.create_user(email="status@test.com", password="pw12345")
        self.report = _make_report(self.user)
        self.client.force_login(self.user)

    def _status(self, run):
        from django.urls import reverse
        url = reverse('reporting:report_run_status', args=[self.report.uuid, run.id])
        return self.client.get(url, HTTP_HOST='localhost').json()

    def test_pending_running_complete_failed(self):
        from django.utils import timezone
        from reporting.models import ReportRun
        pending = ReportRun.objects.create(report=self.report, user=self.user)
        self.assertEqual(self._status(pending)['status'], 'pending')

        running = ReportRun.objects.create(
            report=self.report, user=self.user,
            status=ReportRun.STATUS_RUNNING, started_at=timezone.now(),
        )
        self.assertEqual(self._status(running)['status'], 'running')

        complete = ReportRun.objects.create(
            report=self.report, user=self.user,
            status=ReportRun.STATUS_COMPLETE, row_count=5,
        )
        body = self._status(complete)
        self.assertEqual(body['status'], 'complete')
        self.assertIn('result_url', body)

        failed = ReportRun.objects.create(
            report=self.report, user=self.user,
            status=ReportRun.STATUS_FAILED, error_message="nope",
        )
        self.assertEqual(self._status(failed)['status'], 'failed')
