from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus
from jobtracker.models import AwardingBody, Qualification, QualificationRecord, QualificationTag


class QualificationTagTests(TestCase):
    def test_tag_creation(self):
        tag = QualificationTag.objects.create(name="Security")
        self.assertEqual(tag.name, "Security")
        self.assertTrue(tag.slug)

    def test_tag_str(self):
        tag = QualificationTag.objects.create(name="Security")
        self.assertEqual(str(tag), "Security")


class AwardingBodyTests(TestCase):
    def test_awarding_body_creation(self):
        body = AwardingBody.objects.create(
            name="CREST",
            description="Council of Registered Ethical Security Testers",
            url="https://www.crest-approved.org",
        )
        self.assertEqual(body.name, "CREST")
        self.assertEqual(body.description, "Council of Registered Ethical Security Testers")
        self.assertEqual(body.url, "https://www.crest-approved.org")

    def test_awarding_body_auto_slug(self):
        body = AwardingBody.objects.create(name="CREST")
        self.assertTrue(body.slug)

    def test_awarding_body_str(self):
        body = AwardingBody.objects.create(name="CREST")
        self.assertEqual(str(body), "CREST")


class QualificationTests(TestCase):
    def setUp(self):
        self.body = AwardingBody.objects.create(name="CREST")
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")

    def test_qualification_creation(self):
        qual = Qualification.objects.create(
            awarding_body=self.body,
            name="CRT",
            short_name="CRT",
            validity_period=1095,
            verification_required=True,
        )
        self.assertEqual(qual.name, "CRT")
        self.assertEqual(qual.short_name, "CRT")
        self.assertEqual(qual.validity_period, 1095)
        self.assertTrue(qual.verification_required)

    def test_qualification_auto_slug(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT"
        )
        self.assertTrue(qual.slug)

    def test_qualification_str_with_short_name(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="Certified Registered Tester", short_name="CRT"
        )
        self.assertEqual(str(qual), "Certified Registered Tester (CRT)")

    def test_qualification_str_without_short_name(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="CPSA", short_name=""
        )
        self.assertEqual(str(qual), "CPSA")

    def test_get_absolute_url(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT"
        )
        url = qual.get_absolute_url()
        self.assertIn(self.body.slug, url)
        self.assertIn(qual.slug, url)

    def test_validity_period_display_years_months_days(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="Q1", validity_period=1095
        )
        self.assertEqual(qual.validity_period_display, "3 years")

    def test_validity_period_display_no_expiry(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="Q2", validity_period=None
        )
        self.assertEqual(qual.validity_period_display, "Does not expire")

    def test_validity_period_display_mixed(self):
        # 1 year, 2 months, 15 days = 365 + 60 + 15 = 440
        qual = Qualification.objects.create(
            awarding_body=self.body, name="Q3", validity_period=440
        )
        self.assertEqual(qual.validity_period_display, "1 year, 2 months, 15 days")

    def test_awarded_count(self):
        qual = Qualification.objects.create(awarding_body=self.body, name="Q4")
        QualificationRecord.objects.create(
            qualification=qual, user=self.user, status=QualificationStatus.AWARDED
        )
        self.assertEqual(qual.awarded_count(), 1)

    def test_in_progress_count(self):
        qual = Qualification.objects.create(awarding_body=self.body, name="Q5")
        QualificationRecord.objects.create(
            qualification=qual, user=self.user, status=QualificationStatus.IN_PROGRESS
        )
        self.assertEqual(qual.in_progress_count(), 1)

    def test_lapsed_count(self):
        qual = Qualification.objects.create(awarding_body=self.body, name="Q6")
        QualificationRecord.objects.create(
            qualification=qual, user=self.user, status=QualificationStatus.LAPSED
        )
        self.assertEqual(qual.lapsed_count(), 1)

    def test_expiring_soon_count(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="Q7", validity_period=1095
        )
        QualificationRecord.objects.create(
            qualification=qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() + timedelta(days=30),
        )
        self.assertEqual(qual.expiring_soon_count(), 1)

    def test_expiring_soon_count_excludes_past(self):
        qual = Qualification.objects.create(
            awarding_body=self.body, name="Q8", validity_period=1095
        )
        QualificationRecord.objects.create(
            qualification=qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() - timedelta(days=5),
        )
        self.assertEqual(qual.expiring_soon_count(), 0)


class QualificationRecordTests(TestCase):
    def setUp(self):
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")

    def test_record_creation(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        self.assertEqual(record.qualification, self.qual)
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.status, QualificationStatus.IN_PROGRESS)

    def test_record_str(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        s = str(record)
        self.assertIn("Awarded", s)

    def test_status_bs_colour(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        self.assertEqual(record.status_bs_colour, "success")

    def test_is_lapsed_true(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() - timedelta(days=1),
        )
        self.assertTrue(record.is_lapsed())

    def test_is_lapsed_false(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() + timedelta(days=30),
        )
        self.assertFalse(record.is_lapsed())

    def test_is_lapsed_no_date(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
        )
        self.assertFalse(record.is_lapsed())

    def test_days_to_lapse(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() + timedelta(days=45),
        )
        self.assertEqual(record.days_to_lapse(), 45)

    def test_days_to_lapse_past(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() - timedelta(days=10),
        )
        self.assertEqual(record.days_to_lapse(), 0)

    def test_days_to_lapse_no_date(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
        )
        self.assertEqual(record.days_to_lapse(), 9999)

    def test_expiry_urgency_expired(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() - timedelta(days=1),
        )
        self.assertEqual(record.expiry_urgency, "expired")

    def test_expiry_urgency_critical(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() + timedelta(days=15),
        )
        self.assertEqual(record.expiry_urgency, "critical")

    def test_expiry_urgency_warning(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() + timedelta(days=60),
        )
        self.assertEqual(record.expiry_urgency, "warning")

    def test_expiry_urgency_ok(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            lapse_date=timezone.now().date() + timedelta(days=180),
        )
        self.assertEqual(record.expiry_urgency, "ok")

    def test_expiry_urgency_no_expiry(self):
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
        )
        self.assertEqual(record.expiry_urgency, "no_expiry")

    def test_clean_duplicate_active_record(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        duplicate = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_clean_allows_different_qualification(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        other_qual = Qualification.objects.create(
            awarding_body=self.body, name="CPSA", short_name="CPSA"
        )
        record = QualificationRecord(
            qualification=other_qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        record.clean()  # Should not raise

    def test_clean_allows_inactive_duplicate(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.UNSUCCESSFUL,
        )
        record = QualificationRecord(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        record.clean()  # Should not raise

    def test_clean_no_user_skips_validation(self):
        record = QualificationRecord(
            qualification=self.qual,
            status=QualificationStatus.IN_PROGRESS,
        )
        record.clean()  # Should not raise
