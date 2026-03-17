from datetime import timedelta

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone

from chaotica_utils.models import User
from chaotica_utils.models.job_levels import JobLevel, UserJobLevel


class JobLevelTests(TestCase):
    def test_creation(self):
        level = JobLevel.objects.create(
            short_label="JL1", long_label="Senior", order=1, is_active=True
        )
        self.assertEqual(level.short_label, "JL1")
        self.assertEqual(level.long_label, "Senior")
        self.assertTrue(level.is_active)

    def test_str_with_long_label(self):
        level = JobLevel.objects.create(
            short_label="JL1", long_label="Senior", order=1
        )
        self.assertEqual(str(level), "JL1 - Senior")

    def test_str_without_long_label(self):
        level = JobLevel.objects.create(
            short_label="JL1", long_label=None, order=1
        )
        self.assertEqual(str(level), "JL1")

    def test_ordering(self):
        JobLevel.objects.create(short_label="JL2", order=2)
        JobLevel.objects.create(short_label="JL1", order=1)
        levels = list(JobLevel.objects.all())
        self.assertEqual(levels[0].short_label, "JL1")
        self.assertEqual(levels[1].short_label, "JL2")

    def test_clean_zero_order_raises(self):
        level = JobLevel(short_label="X", order=0)
        with self.assertRaises(ValidationError):
            level.clean()

    def test_get_next_order_empty_table(self):
        JobLevel.objects.all().delete()
        self.assertEqual(JobLevel.get_next_order(), 1)

    def test_get_next_order_existing(self):
        JobLevel.objects.create(short_label="JL5", order=5)
        self.assertEqual(JobLevel.get_next_order(), 6)


class UserJobLevelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.level = JobLevel.objects.create(
            short_label="JL1", long_label="Senior", order=1, is_active=True
        )
        self.level2 = JobLevel.objects.create(
            short_label="JL2", long_label="Lead", order=2, is_active=True
        )

    def test_creation(self):
        assignment = UserJobLevel.objects.create(
            user=self.user, job_level=self.level, is_current=True
        )
        self.assertEqual(assignment.user, self.user)
        self.assertEqual(assignment.job_level, self.level)
        self.assertTrue(assignment.is_current)

    def test_str(self):
        assignment = UserJobLevel.objects.create(
            user=self.user, job_level=self.level, is_current=True
        )
        self.assertEqual(str(assignment), "testuser@test.com - JL1 (Current)")

    def test_clean_future_date_raises(self):
        assignment = UserJobLevel(
            user=self.user,
            job_level=self.level,
            assigned_date=timezone.now().date() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_save_unsets_previous_current(self):
        first = UserJobLevel.objects.create(
            user=self.user, job_level=self.level, is_current=True
        )
        UserJobLevel.objects.create(
            user=self.user, job_level=self.level2, is_current=True
        )
        first.refresh_from_db()
        self.assertFalse(first.is_current)

    def test_get_current_level(self):
        UserJobLevel.objects.create(
            user=self.user, job_level=self.level, is_current=True
        )
        current = UserJobLevel.get_current_level(self.user)
        self.assertIsNotNone(current)
        self.assertEqual(current.job_level, self.level)

    def test_get_current_level_none(self):
        current = UserJobLevel.get_current_level(self.user)
        self.assertIsNone(current)

    def test_assign_level(self):
        assignment = UserJobLevel.assign_level(self.user, self.level)
        self.assertTrue(assignment.is_current)
        self.assertEqual(assignment.job_level, self.level)

    def test_assign_level_unsets_previous(self):
        first = UserJobLevel.assign_level(self.user, self.level)
        UserJobLevel.assign_level(self.user, self.level2)
        first.refresh_from_db()
        self.assertFalse(first.is_current)
