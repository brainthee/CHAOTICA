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
