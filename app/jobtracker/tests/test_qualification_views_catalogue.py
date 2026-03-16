from django.test import TestCase, Client as TestClient
from django.urls import reverse
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus
from jobtracker.models import AwardingBody, Qualification, QualificationRecord


class QualificationViewTestCase(TestCase):
    """Base class that sets HTTP_HOST to satisfy custom SessionMiddleware."""

    def setUp(self):
        super().setUp()
        self.client = TestClient(HTTP_HOST="testserver")


class QualificationListViewTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        assign_perm("jobtracker.view_qualification", self.user)
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )

    def test_list_requires_login(self):
        # PermissionRequiredMixin with return_403=True returns 403 for anon
        resp = self.client.get(reverse("qualification_list"))
        self.assertIn(resp.status_code, [302, 403])

    def test_list_view_success(self):
        self.client.login(email="user@test.com", password="testpass123")
        resp = self.client.get(reverse("qualification_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "jobtracker/qualification_list.html")

    def test_list_view_context(self):
        self.client.login(email="user@test.com", password="testpass123")
        resp = self.client.get(reverse("qualification_list"))
        self.assertEqual(resp.context["total_qualifications"], 1)
        self.assertIn("total_qualified_users", resp.context)
        self.assertIn("tags", resp.context)


class QualificationDetailViewTests(QualificationViewTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="user@test.com", password="testpass123")
        assign_perm("jobtracker.view_qualification", self.user)
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="CRT", short_name="CRT", validity_period=1095
        )

    def _detail_url(self):
        return reverse(
            "qualification_detail",
            kwargs={"bodySlug": self.body.slug, "slug": self.qual.slug},
        )

    def test_detail_requires_login(self):
        resp = self.client.get(self._detail_url())
        self.assertIn(resp.status_code, [302, 403])

    def test_detail_view_success(self):
        self.client.login(email="user@test.com", password="testpass123")
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "jobtracker/qualification_detail.html")

    def test_detail_view_context_counts(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        self.client.login(email="user@test.com", password="testpass123")
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.context["awarded_count"], 1)
        self.assertEqual(resp.context["in_progress_count"], 0)
        self.assertEqual(resp.context["lapsed_count"], 0)

    def test_detail_view_record_tabs(self):
        QualificationRecord.objects.create(
            qualification=self.qual,
            user=self.user,
            status=QualificationStatus.AWARDED,
        )
        self.client.login(email="user@test.com", password="testpass123")
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.context["awarded_records"].count(), 1)
        self.assertEqual(resp.context["in_progress_records"].count(), 0)
        self.assertEqual(resp.context["all_records"].count(), 1)
