from datetime import date, datetime, timezone, timedelta

from django.test import TestCase
from django.core.exceptions import SuspiciousOperation
from django.contrib.auth.models import AnonymousUser
from django.utils.timezone import make_aware

from chaotica_utils.models import User
from chaotica_utils.utils.common import (
    unique_slug_generator,
    calculate_percentage,
    get_start_of_week,
    is_valid_uuid,
    clean_int,
    clean_date,
    clean_fullcalendar_datetime,
    last_day_of_month,
    can_manage_user,
    get_sentinel_user,
)


class UniqueSlugGeneratorTests(TestCase):
    def test_generates_slug_from_value(self):
        from jobtracker.models import AwardingBody

        body = AwardingBody(name="Test")
        slug = unique_slug_generator(body, "Hello World")
        self.assertEqual(slug, "hello-world")

    def test_handles_collision(self):
        from jobtracker.models import AwardingBody

        AwardingBody.objects.create(name="Test Body", slug="test-body")
        body = AwardingBody(name="Another")
        slug = unique_slug_generator(body, "Test Body")
        self.assertEqual(slug, "test-body-1")

    def test_special_characters(self):
        from jobtracker.models import AwardingBody

        body = AwardingBody(name="Test")
        slug = unique_slug_generator(body, "Hello! @World #2024")
        self.assertEqual(slug, "hello-world-2024")


class CalculatePercentageTests(TestCase):
    def test_basic_percentage(self):
        self.assertEqual(calculate_percentage(50, 100), 50.0)

    def test_zero_whole_raises(self):
        with self.assertRaises(ZeroDivisionError):
            calculate_percentage(50, 0)

    def test_negative_decimal_raises(self):
        with self.assertRaises(ValueError):
            calculate_percentage(50, 100, decimal_places=-1)

    def test_custom_decimal_places(self):
        result = calculate_percentage(1, 3, decimal_places=3)
        self.assertEqual(result, 33.333)


class GetStartOfWeekTests(TestCase):
    def test_returns_monday(self):
        # 2024-01-10 is a Wednesday
        dt = make_aware(datetime(2024, 1, 10))
        result = get_start_of_week(dt)
        self.assertEqual(result, date(2024, 1, 8))

    def test_monday_returns_itself(self):
        # 2024-01-08 is a Monday
        dt = make_aware(datetime(2024, 1, 8))
        result = get_start_of_week(dt)
        self.assertEqual(result, date(2024, 1, 8))

    def test_none_returns_current_week(self):
        result = get_start_of_week(None)
        self.assertEqual(result.weekday(), 0)


class IsValidUuidTests(TestCase):
    def test_valid_uuid(self):
        self.assertTrue(is_valid_uuid("c9bf9e57-1685-4c89-bafb-ff5af830be8a"))

    def test_invalid_uuid(self):
        self.assertFalse(is_valid_uuid("not-a-uuid"))

    def test_short_string(self):
        self.assertFalse(is_valid_uuid("c9bf9e58"))


class CleanIntTests(TestCase):
    def test_valid_int(self):
        self.assertEqual(clean_int("42"), 42)

    def test_none_returns_none(self):
        self.assertIsNone(clean_int(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(clean_int(""))

    def test_invalid_raises_suspicious(self):
        with self.assertRaises(SuspiciousOperation):
            clean_int("abc")


class CleanDateTests(TestCase):
    def test_valid_date(self):
        self.assertEqual(clean_date("2024-01-15"), date(2024, 1, 15))

    def test_none_returns_none(self):
        self.assertIsNone(clean_date(None))


class CleanFullcalendarDatetimeTests(TestCase):
    def test_iso8601_with_offset(self):
        result = clean_fullcalendar_datetime("2023-10-23T00:00:00+01:00")
        self.assertIsNotNone(result)
        self.assertTrue(result.tzinfo is not None)

    def test_iso8601_utc_z(self):
        result = clean_fullcalendar_datetime("2023-10-30T00:00:00Z")
        self.assertIsNotNone(result)
        self.assertTrue(result.tzinfo is not None)

    def test_none_returns_none(self):
        self.assertIsNone(clean_fullcalendar_datetime(None))

    def test_invalid_raises_suspicious(self):
        with self.assertRaises(SuspiciousOperation):
            clean_fullcalendar_datetime("not-a-date")


class LastDayOfMonthTests(TestCase):
    def test_january(self):
        self.assertEqual(last_day_of_month(date(2024, 1, 15)), date(2024, 1, 31))

    def test_february_leap(self):
        self.assertEqual(last_day_of_month(date(2024, 2, 1)), date(2024, 2, 29))

    def test_february_non_leap(self):
        self.assertEqual(last_day_of_month(date(2023, 2, 1)), date(2023, 2, 28))


class CanManageUserTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@test.com", password="testpass123"
        )
        self.manager = User.objects.create_user(
            email="manager@test.com", password="testpass123"
        )
        self.other = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )

    def test_self_management(self):
        result = can_manage_user(self.user, self.user)
        self.assertEqual(result, self.user)

    def test_manager_can_manage(self):
        self.user.manager = self.manager
        self.user.save()
        result = can_manage_user(self.manager, self.user)
        self.assertEqual(result, self.user)

    def test_acting_manager_can_manage(self):
        self.user.acting_manager = self.manager
        self.user.save()
        result = can_manage_user(self.manager, self.user)
        self.assertEqual(result, self.user)

    def test_unrelated_user_returns_none(self):
        result = can_manage_user(self.other, self.user)
        self.assertIsNone(result)

    def test_unauthenticated_returns_none(self):
        result = can_manage_user(AnonymousUser(), self.user)
        self.assertIsNone(result)

    def test_email_string_lookup(self):
        result = can_manage_user(self.user, "user@test.com")
        self.assertEqual(result, self.user)


class GetSentinelUserTests(TestCase):
    def test_returns_sentinel_with_correct_email(self):
        # Create the sentinel user explicitly to avoid MySQL auto-increment
        # PK collisions that occur with get_or_create + --keepdb.
        User.objects.create_user(email="deleted@chaotica.app", password="x")
        sentinel = get_sentinel_user()
        self.assertEqual(sentinel.email, "deleted@chaotica.app")

    def test_idempotent(self):
        User.objects.create_user(email="deleted@chaotica.app", password="x")
        sentinel1 = get_sentinel_user()
        sentinel2 = get_sentinel_user()
        self.assertEqual(sentinel1.pk, sentinel2.pk)
