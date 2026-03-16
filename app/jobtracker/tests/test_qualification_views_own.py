from datetime import timedelta

from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus
from jobtracker.models import AwardingBody, Qualification, QualificationRecord


class QualificationViewTestCase(TestCase):
    """Base class that sets HTTP_HOST to satisfy custom SessionMiddleware."""

    def setUp(self):
        super().setUp()
        self.client = TestClient(HTTP_HOST="testserver")


class OwnQualificationAuthTests(QualificationViewTestCase):
    def test_list_requires_login(self):
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_add_requires_login(self):
        resp = self.client.get(reverse("add_own_qualification"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_update_requires_login(self):
        resp = self.client.get(reverse("update_own_qualification", args=[1]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_transition_requires_login(self):
        resp = self.client.post(
            reverse("transition_own_qualification", args=[1, "mark_awarded"])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)


class OwnQualificationListViewTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.other_user = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.client.login(email="user@test.com", password="testpass123")

    def test_list_view_success(self):
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "jobtracker/qualificationrecord_list.html")

    def test_list_view_context_counts(self):
        QualificationRecord.objects.create(
            qualification=self.qual, user=self.user, status=QualificationStatus.AWARDED
        )
        QualificationRecord.objects.create(
            qualification=Qualification.objects.create(
                awarding_body=self.body, name="CPSA", short_name="CPSA"
            ),
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertEqual(resp.context["awarded_count"], 1)
        self.assertEqual(resp.context["in_progress_count"], 1)

    def test_list_view_only_own_records(self):
        QualificationRecord.objects.create(
            qualification=self.qual, user=self.other_user, status=QualificationStatus.AWARDED
        )
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertEqual(len(resp.context["object_list"]), 0)

    def test_list_view_has_direct_reports_true(self):
        self.other_user.manager = self.user
        self.other_user.save()
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertTrue(resp.context["has_direct_reports"])

    def test_list_view_has_direct_reports_false(self):
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertFalse(resp.context["has_direct_reports"])

    def test_list_view_expiring_records(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() + timedelta(days=60),
        )
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertEqual(resp.context["expiring_count"], 1)
        self.assertEqual(resp.context["expiring_records"].count(), 1)

    def test_list_view_critical_records(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            lapse_date=timezone.now().date() + timedelta(days=15),
        )
        resp = self.client.get(reverse("view_own_qualifications"))
        self.assertEqual(resp.context["critical_records"].count(), 1)


class AddOwnQualificationTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.qual_no_expiry = Qualification.objects.create(
            awarding_body=self.body, name="CPSA", short_name="CPSA"
        )
        self.client.login(email="user@test.com", password="testpass123")

    def test_add_get_returns_form(self):
        resp = self.client.get(reverse("add_own_qualification"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("html_form", data)

    def test_add_post_valid(self):
        resp = self.client.post(
            reverse("add_own_qualification"),
            {"qualification": self.qual.pk, "status": QualificationStatus.IN_PROGRESS},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["form_is_valid"])
        record = QualificationRecord.objects.get(user=self.user, qualification=self.qual)
        self.assertEqual(record.status, QualificationStatus.IN_PROGRESS)

    def test_add_post_auto_calculates_lapse_date(self):
        today = timezone.now().date()
        resp = self.client.post(
            reverse("add_own_qualification"),
            {
                "qualification": self.qual.pk,
                "status": QualificationStatus.IN_PROGRESS,
                "awarded_date": today.strftime("%Y-%m-%d"),
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])
        record = QualificationRecord.objects.get(user=self.user)
        self.assertEqual(record.lapse_date, today + timedelta(days=1095))

    def test_add_post_no_lapse_date_without_validity(self):
        today = timezone.now().date()
        resp = self.client.post(
            reverse("add_own_qualification"),
            {
                "qualification": self.qual_no_expiry.pk,
                "status": QualificationStatus.IN_PROGRESS,
                "awarded_date": today.strftime("%Y-%m-%d"),
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])
        record = QualificationRecord.objects.get(user=self.user)
        self.assertIsNone(record.lapse_date)

    def test_add_post_invalid_form(self):
        resp = self.client.post(
            reverse("add_own_qualification"),
            {"status": QualificationStatus.IN_PROGRESS},
            # missing qualification
        )
        data = resp.json()
        self.assertNotIn("form_is_valid", data)
        self.assertIn("html_form", data)


class UpdateOwnQualificationTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.other_user = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        self.client.login(email="user@test.com", password="testpass123")

    def test_update_get_returns_form(self):
        resp = self.client.get(reverse("update_own_qualification", args=[self.record.pk]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("html_form", data)

    def test_update_post_valid(self):
        resp = self.client.post(
            reverse("update_own_qualification", args=[self.record.pk]),
            {
                "qualification": self.qual.pk,
                "status": QualificationStatus.ATTEMPTED,
                "notes": "Updated note",
            },
        )
        data = resp.json()
        self.assertTrue(data["form_is_valid"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.notes, "Updated note")

    def test_update_recalculates_lapse_on_date_change(self):
        self.record.status = QualificationStatus.ATTEMPTED
        self.record.save()
        new_date = timezone.now().date() - timedelta(days=10)
        resp = self.client.post(
            reverse("update_own_qualification", args=[self.record.pk]),
            {
                "qualification": self.qual.pk,
                "status": QualificationStatus.ATTEMPTED,
                "awarded_date": new_date.strftime("%Y-%m-%d"),
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.lapse_date, new_date + timedelta(days=1095))

    def test_update_other_users_record_404(self):
        other_record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.other_user,
            status=QualificationStatus.IN_PROGRESS,
        )
        resp = self.client.get(reverse("update_own_qualification", args=[other_record.pk]))
        self.assertEqual(resp.status_code, 404)


class TransitionOwnQualificationTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.other_user = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.client.login(email="user@test.com", password="testpass123")

    def _create_record(self, status):
        return QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=status,
        )

    def test_transition_mark_attempted(self):
        record = self._create_record(QualificationStatus.IN_PROGRESS)
        today = timezone.now().date()
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_attempted"]),
            {"attempt_date": today.strftime("%Y-%m-%d")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.ATTEMPTED)
        self.assertEqual(record.attempt_date, today)

    def test_transition_mark_awarded(self):
        record = self._create_record(QualificationStatus.ATTEMPTED)
        record.attempt_date = timezone.now().date() - timedelta(days=5)
        record.save()
        today = timezone.now().date()
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_awarded"]),
            {"awarded_date": today.strftime("%Y-%m-%d")},
        )
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.AWARDED)
        self.assertEqual(record.lapse_date, today + timedelta(days=1095))

    def test_transition_mark_unsuccessful(self):
        record = self._create_record(QualificationStatus.ATTEMPTED)
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_unsuccessful"]),
        )
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.UNSUCCESSFUL)

    def test_transition_start_renewal(self):
        record = self._create_record(QualificationStatus.LAPSED)
        record.verified_by = self.user
        record.verified_on = timezone.now()
        record.save()
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "start_renewal"]),
        )
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, QualificationStatus.IN_PROGRESS)
        self.assertIsNone(record.verified_by)
        self.assertIsNone(record.verified_on)

    def test_transition_invalid_action(self):
        record = self._create_record(QualificationStatus.IN_PROGRESS)
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "bogus_action"]),
        )
        self.assertEqual(resp.status_code, 400)

    def test_transition_not_allowed(self):
        record = self._create_record(QualificationStatus.AWARDED)
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_attempted"]),
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("error", data)

    def test_transition_future_attempt_date(self):
        record = self._create_record(QualificationStatus.IN_PROGRESS)
        future = timezone.now().date() + timedelta(days=5)
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_attempted"]),
            {"attempt_date": future.strftime("%Y-%m-%d")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_transition_future_awarded_date(self):
        record = self._create_record(QualificationStatus.ATTEMPTED)
        future = timezone.now().date() + timedelta(days=5)
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_awarded"]),
            {"awarded_date": future.strftime("%Y-%m-%d")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_transition_awarded_before_attempt(self):
        record = self._create_record(QualificationStatus.ATTEMPTED)
        record.attempt_date = timezone.now().date()
        record.save()
        earlier = timezone.now().date() - timedelta(days=5)
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_awarded"]),
            {"awarded_date": earlier.strftime("%Y-%m-%d")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_transition_other_users_record_404(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.other_user,
            status=QualificationStatus.IN_PROGRESS,
        )
        resp = self.client.post(
            reverse("transition_own_qualification", args=[record.pk, "mark_attempted"]),
        )
        self.assertEqual(resp.status_code, 404)

    def test_transition_get_not_allowed(self):
        record = self._create_record(QualificationStatus.IN_PROGRESS)
        resp = self.client.get(
            reverse("transition_own_qualification", args=[record.pk, "mark_attempted"]),
        )
        self.assertEqual(resp.status_code, 405)
