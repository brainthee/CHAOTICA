"""Impersonation is superuser-only and every session start is audited."""

from django.test import TestCase, override_settings
from django.urls import reverse

from chaotica_utils.models import User, AuditEvent, AuditCategory


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class ImpersonationTests(TestCase):
    def setUp(self):
        # create_user makes the first user a superuser.
        self.superuser = User.objects.create_user(email="su@test.com", password="pw12345")
        self.staff = User.objects.create_user(email="staff@test.com", password="pw12345")
        self.staff.is_staff = True
        self.staff.save()
        self.target = User.objects.create_user(email="t@test.com", password="pw12345")

    def _start(self, user):
        self.client.force_login(user)
        return self.client.get(
            reverse("impersonate-start", args=[self.target.pk]), HTTP_HOST="testserver"
        )

    def test_staff_cannot_impersonate(self):
        self._start(self.staff)
        self.assertNotIn("_impersonate", self.client.session)

    def test_superuser_impersonation_is_audited(self):
        self._start(self.superuser)
        self.assertIn("_impersonate", self.client.session)
        event = AuditEvent.objects.filter(
            category=AuditCategory.SECURITY, actor=self.superuser
        ).last()
        self.assertIsNotNone(event)
        self.assertEqual(event.metadata.get("impersonation"), "started")
