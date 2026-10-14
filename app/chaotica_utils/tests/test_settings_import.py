"""The site-data importer must be gated on manage_site_settings and must never
let a CSV change privilege flags (is_superuser / is_staff / is_active)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class SettingsImportGateTests(TestCase):
    def setUp(self):
        # First user is auto-promoted to superuser; keep it out of the way.
        User.objects.create_user(email="bootstrap@test.com", password="pw12345")
        self.user = User.objects.create_user(email="u@test.com", password="pw12345")
        self.admin = User.objects.create_user(email="a@test.com", password="pw12345")
        assign_perm("chaotica_utils.manage_site_settings", self.admin)

    def _csv(self, body):
        return SimpleUploadedFile("users.csv", body.encode(), "text/csv")

    def _post(self, body):
        return self.client.post(
            reverse("settings_import_data"),
            {"importType": "CSVUserImporter", "importFiles": self._csv(body)},
            HTTP_HOST="testserver",
        )

    def test_plain_user_cannot_import(self):
        self.client.force_login(self.user)
        resp = self._post("email,is_superuser,is_staff\nu@test.com,True,True\n")
        self.assertEqual(resp.status_code, 403)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)

    def test_privilege_columns_are_ignored(self):
        self.client.force_login(self.admin)
        resp = self._post(
            "email,job_title,is_superuser,is_staff,is_active\n"
            "u@test.com,Tester,True,True,False\n"
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.job_title, "Tester")
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)
        self.assertTrue(self.user.is_active)

    def test_unknown_manager_is_not_created(self):
        self.client.force_login(self.admin)
        self._post("email,manager\nu@test.com,nobody@test.com\n")
        self.assertFalse(User.objects.filter(email__iexact="nobody@test.com").exists())
        self.user.refresh_from_db()
        self.assertIsNone(self.user.manager)
