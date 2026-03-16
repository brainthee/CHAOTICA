from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus
from jobtracker.models import AwardingBody, Qualification, QualificationRecord
from jobtracker.tasks import task_check_qualification_expiry


class TaskCheckQualificationExpiryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.task = task_check_qualification_expiry()

    def test_lapses_expired_awarded_records(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() - timedelta(days=1),
        )
        self.task.do()
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.LAPSED)

    def test_does_not_lapse_future_dates(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() + timedelta(days=30),
        )
        self.task.do()
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.AWARDED)

    def test_does_not_lapse_non_awarded(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
            lapse_date=timezone.now().date() - timedelta(days=1),
        )
        self.task.do()
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.IN_PROGRESS)

    def test_does_not_lapse_null_dates(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=None,
        )
        self.task.do()
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.AWARDED)

    def test_lapse_count_logged(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() - timedelta(days=1),
        )
        user2 = User.objects.create_user(email="user2@test.com", password="testpass123")
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=user2,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() - timedelta(days=5),
        )
        with self.assertLogs("jobtracker.tasks", level="INFO") as cm:
            self.task.do()
        self.assertTrue(any("2" in msg for msg in cm.output))
