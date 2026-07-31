"""Tests for the versioned read-only /api/v1/ API.

Covers the guarantees that matter for this API: authentication is required,
endpoints are read-only, responses are clean JSON (no DataTables/HTML metadata),
access is scoped by the same guardian permissions the UI uses, and sensitive
fields are never serialized.
"""

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from chaotica_utils.models import User
from chaotica_utils.models.job_levels import JobLevel, UserJobLevel
from jobtracker.models import Skill, SkillCategory, UserSkill

from .api.v1.serializers import QualificationRecordSerializer, UserSerializer


# The custom SessionMiddleware validates the HTTP_HOST header (rejecting requests
# without one with a 400). Django's test client sends SERVER_NAME but no HTTP_HOST,
# so we set one explicitly; "testserver" is also pinned into ALLOWED_HOSTS for envs
# whose ALLOWED_HOSTS doesn't include a wildcard.
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class APIV1BaseTest(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient(HTTP_HOST="testserver")

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin"
        )
        cls.normal = User.objects.create_user(
            email="normal@example.com", password="pw-normal"
        )
        cls.category = SkillCategory.objects.create(name="Web")
        cls.skill = Skill.objects.create(name="XSS", category=cls.category)
        cls.user_skill = UserSkill.objects.create(
            user=cls.normal, skill=cls.skill, rating=2
        )


class AuthAndShapeTests(APIV1BaseTest):
    def test_requires_authentication(self):
        resp = self.client.get("/api/v1/skills/")
        self.assertIn(
            resp.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_token_obtain_and_use(self):
        resp = self.client.post(
            "/api/v1/auth/token/",
            {"username": "admin@example.com", "password": "pw-admin"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("token", resp.data)

        token = resp.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        listed = self.client.get("/api/v1/skills/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)

    def test_read_only_post_returns_405(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post("/api/v1/skills/", {"name": "SQLi"})
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_clean_paginated_shape(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/timeslot-types/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Standard DRF page-number shape, not the datatables shape.
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        for row in resp.data["results"]:
            self.assertNotIn("DT_RowId", row)
            self.assertNotIn("DT_RowAttr", row)


class ScopingTests(APIV1BaseTest):
    def test_superuser_sees_all_skills(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/skills/")
        self.assertEqual(resp.data["count"], 1)

    def test_unprivileged_user_sees_no_skills(self):
        # No guardian/global view_skill permission -> empty, never leaks.
        self.client.force_authenticate(self.normal)
        resp = self.client.get("/api/v1/skills/")
        self.assertEqual(resp.data["count"], 0)

    def test_user_sees_own_user_skill(self):
        self.client.force_authenticate(self.normal)
        resp = self.client.get("/api/v1/user-skills/")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["user"], self.normal.pk)

    def test_user_does_not_see_others_user_skill(self):
        other = User.objects.create_user(
            email="other@example.com", password="pw-other"
        )
        UserSkill.objects.create(user=other, skill=self.skill, rating=3)
        self.client.force_authenticate(self.normal)
        resp = self.client.get("/api/v1/user-skills/")
        user_pks = {row["user"] for row in resp.data["results"]}
        self.assertNotIn(other.pk, user_pks)
        self.assertIn(self.normal.pk, user_pks)


class UserJobFieldsTests(APIV1BaseTest):
    def test_job_title_and_level_serialized(self):
        level = JobLevel.objects.create(
            short_label="JL5", long_label="Consultant", order=5
        )
        self.normal.job_title = "Senior Consultant"
        self.normal.save()
        UserJobLevel.objects.create(
            user=self.normal, job_level=level, is_current=True
        )

        self.client.force_authenticate(self.superuser)
        resp = self.client.get(f"/api/v1/users/{self.normal.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["job_title"], "Senior Consultant")
        self.assertEqual(resp.data["job_level"], "JL5")
        self.assertEqual(resp.data["job_level_label"], "Consultant")

    def test_level_null_when_unset(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get(f"/api/v1/users/{self.normal.pk}/")
        self.assertIsNone(resp.data["job_level"])
        self.assertIsNone(resp.data["job_level_label"])


class SetStatusActionTests(APIV1BaseTest):
    def _url(self, user):
        return f"/api/v1/users/{user.pk}/set-status/"

    def test_requires_manage_user_permission(self):
        # normal has no manage_user permission -> forbidden.
        self.client.force_authenticate(self.normal)
        resp = self.client.post(
            self._url(self.superuser), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_can_deactivate_and_reactivate(self):
        target = User.objects.create_user(
            email="target@example.com", password="pw", is_active=True
        )
        self.client.force_authenticate(self.superuser)

        resp = self.client.post(
            self._url(target), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["changed"])
        target.refresh_from_db()
        self.assertFalse(target.is_active)

        resp = self.client.post(
            self._url(target), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_idempotent_no_op(self):
        target = User.objects.create_user(
            email="already@example.com", password="pw", is_active=True
        )
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(target), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["changed"])

    def test_cannot_deactivate_self(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(self.superuser), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_missing_body_is_400(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(self._url(self.normal), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_creation_still_blocked(self):
        # Enabling POST for the action must not open a user-creation route.
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            "/api/v1/users/",
            {"email": "new@example.com", "first_name": "New"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class SensitiveFieldTests(APIV1BaseTest):
    def test_certificate_file_not_serialized(self):
        self.assertNotIn(
            "certificate_file", QualificationRecordSerializer().fields
        )

    def test_user_pii_not_serialized(self):
        fields = set(UserSerializer().fields)
        self.assertNotIn("phone_number", fields)
        self.assertEqual(
            fields,
            {
                "id",
                "first_name",
                "last_name",
                "email",
                "is_active",
                "job_title",
                "job_level",
                "job_level_label",
            },
        )
