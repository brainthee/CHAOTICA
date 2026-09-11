"""Tests for configurable timesheet periods (chaotica_utils.utils.periods)."""

from datetime import date

from constance.test import override_config
from django.test import TestCase

from chaotica_utils.utils.periods import (
    parse_period_start_days,
    period_for_date,
    next_period,
    previous_period,
)

# 1st and 15th — the common two-periods-a-month setup.
DAYS = [1, 15]


class PeriodForDateTests(TestCase):
    def test_first_half_of_month(self):
        self.assertEqual(
            period_for_date(date(2026, 9, 10), DAYS),
            (date(2026, 9, 1), date(2026, 9, 14)),
        )

    def test_boundary_start_inclusive(self):
        self.assertEqual(
            period_for_date(date(2026, 9, 1), DAYS),
            (date(2026, 9, 1), date(2026, 9, 14)),
        )
        self.assertEqual(
            period_for_date(date(2026, 9, 15), DAYS),
            (date(2026, 9, 15), date(2026, 9, 30)),
        )

    def test_second_half_runs_to_month_end(self):
        self.assertEqual(
            period_for_date(date(2026, 9, 30), DAYS),
            (date(2026, 9, 15), date(2026, 9, 30)),
        )

    def test_february_month_end(self):
        # Second period ends on the last day of a short month.
        self.assertEqual(
            period_for_date(date(2026, 2, 20), DAYS),
            (date(2026, 2, 15), date(2026, 2, 28)),
        )

    def test_single_boundary_is_whole_month(self):
        self.assertEqual(
            period_for_date(date(2026, 9, 10), [1]),
            (date(2026, 9, 1), date(2026, 9, 30)),
        )


class PeriodNavigationTests(TestCase):
    def test_next_and_previous_within_month(self):
        self.assertEqual(
            next_period(date(2026, 9, 5), DAYS),
            (date(2026, 9, 15), date(2026, 9, 30)),
        )
        self.assertEqual(
            previous_period(date(2026, 9, 20), DAYS),
            (date(2026, 9, 1), date(2026, 9, 14)),
        )

    def test_next_wraps_to_new_month(self):
        self.assertEqual(
            next_period(date(2026, 9, 20), DAYS),
            (date(2026, 10, 1), date(2026, 10, 14)),
        )

    def test_previous_wraps_to_prior_month(self):
        self.assertEqual(
            previous_period(date(2026, 9, 3), DAYS),
            (date(2026, 8, 15), date(2026, 8, 31)),
        )

    def test_december_to_january_rollover(self):
        self.assertEqual(
            next_period(date(2026, 12, 20), DAYS),
            (date(2027, 1, 1), date(2027, 1, 14)),
        )


class ParseConfigTests(TestCase):
    @override_config(TIMESHEET_PERIOD_START_DAYS="1,15")
    def test_parses_and_sorts(self):
        self.assertEqual(parse_period_start_days(), [1, 15])

    @override_config(TIMESHEET_PERIOD_START_DAYS="15, 1")
    def test_sorts_and_strips(self):
        self.assertEqual(parse_period_start_days(), [1, 15])

    @override_config(TIMESHEET_PERIOD_START_DAYS="")
    def test_empty_falls_back_to_whole_month(self):
        self.assertEqual(parse_period_start_days(), [1])

    @override_config(TIMESHEET_PERIOD_START_DAYS="abc,99,10")
    def test_ignores_invalid_and_out_of_range(self):
        self.assertEqual(parse_period_start_days(), [10])
