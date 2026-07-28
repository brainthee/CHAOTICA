from datetime import date

from django.test import SimpleTestCase

from chaotica_utils.utils.utilisation import (
    UTILISATION_FORMULA_DESCRIPTION,
    calculate_utilisation,
    aggregate_utilisation,
)


# Two weeks: Mon 2026-07-06 .. Sun 2026-07-19. Working week is Mon-Fri.
START = date(2026, 7, 6)
END = date(2026, 7, 19)
WORKING_DAYS = [1, 2, 3, 4, 5]


def _slot(start, end, confirmed=False, tentative=False, non_working=False):
    return {
        "start": start,
        "end": end,
        "is_confirmed": confirmed,
        "is_tentative": tentative,
        "is_non_working_slot": non_working,
    }


def _calc(slots, holidays=None):
    return calculate_utilisation(
        slots, START, END, WORKING_DAYS, holidays or []
    )


class CalculateUtilisationTests(SimpleTestCase):
    def test_baseline_confirmed_days(self):
        # One full confirmed week out of two working weeks -> 50%.
        r = _calc([_slot(date(2026, 7, 6), date(2026, 7, 10), confirmed=True)])
        self.assertEqual(r["working_days"], 10)
        self.assertEqual(r["effective_working_days"], 10)
        self.assertEqual(r["confirmed_days"], 5)
        self.assertEqual(r["utilisation_percentage"], 50.0)

    def test_leave_reduces_denominator(self):
        # Week 1 confirmed, week 2 annual leave -> denominator drops to 5, 100%.
        r = _calc(
            [
                _slot(date(2026, 7, 6), date(2026, 7, 10), confirmed=True),
                _slot(date(2026, 7, 13), date(2026, 7, 17), non_working=True),
            ]
        )
        self.assertEqual(r["effective_working_days"], 5)
        self.assertEqual(r["non_working_slot_days"], 5)
        self.assertEqual(r["utilisation_percentage"], 100.0)

    def test_leave_wins_over_same_day_confirmed(self):
        # A day with both a confirmed slot and a leave slot is excluded entirely.
        r = _calc(
            [
                _slot(date(2026, 7, 6), date(2026, 7, 6), confirmed=True),
                _slot(date(2026, 7, 6), date(2026, 7, 6), non_working=True),
            ]
        )
        self.assertEqual(r["effective_working_days"], 9)
        self.assertEqual(r["confirmed_days"], 0)

    def test_sick_day_reduces_denominator(self):
        # Sick is also a non-working slot type.
        r = _calc([_slot(date(2026, 7, 7), date(2026, 7, 7), non_working=True)])
        self.assertEqual(r["effective_working_days"], 9)
        self.assertEqual(r["non_working_slot_days"], 1)

    def test_public_holiday_excluded(self):
        r = _calc([], holidays=[date(2026, 7, 6)])
        self.assertEqual(r["working_days"], 9)
        self.assertEqual(r["holiday_days"], 1)

    def test_tentative_not_counted_in_utilisation(self):
        r = _calc([_slot(date(2026, 7, 6), date(2026, 7, 10), tentative=True)])
        self.assertEqual(r["tentative_days"], 5)
        self.assertEqual(r["utilisation_percentage"], 0)

    def test_internal_not_in_numerator(self):
        # Working slot with no phase (e.g. training) is internal, not delivery.
        r = _calc([_slot(date(2026, 7, 6), date(2026, 7, 10))])
        self.assertEqual(r["internal_days"], 5)
        self.assertEqual(r["utilisation_percentage"], 0)
        # Backwards-compatible "no client delivery" count still populated.
        self.assertEqual(r["non_delivery_days"], 5)

    def test_fully_on_leave_returns_none(self):
        r = _calc([_slot(date(2026, 7, 6), date(2026, 7, 17), non_working=True)])
        self.assertEqual(r["effective_working_days"], 0)
        self.assertIsNone(r["utilisation_percentage"])
        self.assertIsNone(r["confirmed_percentage"])
        # Non-utilisation percentages stay numeric so chart data doesn't break.
        self.assertEqual(r["available_percentage"], 0)

    def test_weekend_slots_ignored(self):
        # A slot on the weekend contributes nothing.
        r = _calc([_slot(date(2026, 7, 11), date(2026, 7, 12), confirmed=True)])
        self.assertEqual(r["confirmed_days"], 0)
        self.assertEqual(r["non_working_days"], 4)  # two weekends


class WorkingDaysCoercionTests(SimpleTestCase):
    """Real data has units whose businessHours_days is a bare int or JSON
    string rather than a list; the engine must not crash on those."""

    def test_int_working_days(self):
        r = calculate_utilisation(
            [_slot(date(2026, 7, 6), date(2026, 7, 6), confirmed=True)],
            START, END, 1, [],  # only Monday
        )
        # Two Mondays in the fortnight, one confirmed.
        self.assertEqual(r["working_days"], 2)
        self.assertEqual(r["confirmed_days"], 1)

    def test_json_string_working_days(self):
        r = calculate_utilisation([], START, END, "[1, 2, 3, 4, 5]", [])
        self.assertEqual(r["working_days"], 10)

    def test_garbage_working_days_no_crash(self):
        r = calculate_utilisation([], START, END, "not-json", [])
        self.assertEqual(r["working_days"], 0)
        self.assertIsNone(r["utilisation_percentage"])


class AggregateUtilisationTests(SimpleTestCase):
    def test_zero_effective_user_excluded_from_average(self):
        summary = aggregate_utilisation(
            [
                {
                    "working_days": 10,
                    "effective_working_days": 10,
                    "confirmed_days": 5,
                    "available_days": 5,
                },
                {  # fully on leave -> must not drag the average to 0
                    "working_days": 10,
                    "effective_working_days": 0,
                    "confirmed_days": 0,
                    "available_days": 0,
                },
            ]
        )
        self.assertEqual(summary["num_users"], 2)
        self.assertEqual(summary["avg_utilisation_percentage"], 50.0)

    def test_empty_input(self):
        summary = aggregate_utilisation([])
        self.assertEqual(summary["num_users"], 0)
        self.assertEqual(summary["avg_utilisation_percentage"], 0)


class FormulaDescriptionTests(SimpleTestCase):
    def test_description_is_present(self):
        self.assertIn("Utilisation", UTILISATION_FORMULA_DESCRIPTION)
        self.assertIn("effective working days", UTILISATION_FORMULA_DESCRIPTION)
