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


class TeamQualificationListViewTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user(
            email="manager@test.com", password="testpass123"
        )
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.user.manager = self.manager
        self.user.save()
        self.unrelated = User.objects.create_user(
            email="unrelated@test.com", password="testpass123"
        )
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )
        self.qual_verified = Qualification.objects.create(
            awarding_body=self.body,
            name="CCT",
            short_name="CCT",
            validity_period=1095,
            verification_required=True,
        )

    def test_team_view_requires_login(self):
        resp = self.client.get(reverse("view_team_qualifications"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_team_view_success(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.get(reverse("view_team_qualifications"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["object_list"]), 1)

    def test_team_view_acting_manager(self):
        self.user.manager = None
        self.user.acting_manager = self.manager
        self.user.save()
        QualificationRecord.objects.create(
            qualification=self.qual, user=self.user, status=QualificationStatus.AWARDED
        )
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.get(reverse("view_team_qualifications"))
        self.assertEqual(len(resp.context["object_list"]), 1)

    def test_team_view_excludes_non_managed(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.unrelated,
            status=QualificationStatus.AWARDED,
        )
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.get(reverse("view_team_qualifications"))
        self.assertEqual(len(resp.context["object_list"]), 0)

    def test_team_view_context_counts(self):
        QualificationRecord.objects.create(
            qualification=self.qual_verified,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.get(reverse("view_team_qualifications"))
        self.assertEqual(resp.context["awarded_count"], 1)
        self.assertEqual(resp.context["unverified_count"], 1)

    def test_team_view_unverified_count_respects_verification_required(self):
        QualificationRecord.objects.create(
            qualification=self.qual,  # verification_required=False
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.get(reverse("view_team_qualifications"))
        self.assertEqual(resp.context["unverified_count"], 0)


class VerifyQualificationTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user(
            email="manager@test.com", password="testpass123"
        )
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.user.manager = self.manager
        self.user.save()
        self.other = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body,
            name="CCT",
            short_name="CCT",
            verification_required=True,
        )

    def _create_awarded(self, user):
        return QualificationRecord.objects.create(
            qualification=self.qual,
            user=user,
            status=QualificationStatus.AWARDED,
        )

    def test_verify_success(self):
        record = self._create_awarded(self.user)
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.post(reverse("verify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.verified_by, self.manager)
        self.assertIsNotNone(record.verified_on)

    def test_verify_not_manager_forbidden(self):
        record = self._create_awarded(self.user)
        self.client.login(email="other@test.com", password="testpass123")
        resp = self.client.post(reverse("verify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_verify_acting_manager_success(self):
        self.user.manager = None
        self.user.acting_manager = self.manager
        self.user.save()
        record = self._create_awarded(self.user)
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.post(reverse("verify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.verified_by, self.manager)

    def test_verify_non_awarded_404(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.post(reverse("verify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_verify_get_not_allowed(self):
        record = self._create_awarded(self.user)
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.get(reverse("verify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 405)


class UnverifyQualificationTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user(
            email="manager@test.com", password="testpass123"
        )
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        self.user.manager = self.manager
        self.user.save()
        self.other = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body,
            name="CCT",
            short_name="CCT",
            verification_required=True,
        )

    def _create_verified(self):
        return QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
            verified_by=self.manager,
            verified_on=timezone.now(),
        )

    def test_unverify_success(self):
        record = self._create_verified()
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.post(reverse("unverify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertIsNone(record.verified_by)
        self.assertIsNone(record.verified_on)

    def test_unverify_not_manager_forbidden(self):
        record = self._create_verified()
        self.client.login(email="other@test.com", password="testpass123")
        resp = self.client.post(reverse("unverify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_unverify_non_awarded_404(self):
        record = QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.IN_PROGRESS,
        )
        self.client.login(email="manager@test.com", password="testpass123")
        resp = self.client.post(reverse("unverify_qualification", args=[record.pk]))
        self.assertEqual(resp.status_code, 404)
