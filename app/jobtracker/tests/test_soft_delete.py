"""Soft-delete of Client / OrganisationalUnit.

Deleting a client or org unit used to be a hard DB delete that CASCADE-wiped
every job/phase/timeslot/history under it. It is now a soft delete: the row is
hidden from default querysets but its dependents survive.
"""
from django.test import TestCase, Client as HttpClient, override_settings
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.models import Client, Job, OrganisationalUnit


class SoftDeleteModelTests(TestCase):
    def setUp(self):
        self.unit = OrganisationalUnit.objects.create(name="Unit A")
        self.client_obj = Client.objects.create(name="Acme")
        self.superuser = User.objects.create_superuser(
            email="admin@test.com", password="pw12345"
        )
        self.job = Job.objects.create(
            unit=self.unit,
            client=self.client_obj,
            title="J",
            created_by=self.superuser,
            account_manager=self.superuser,
        )

    def test_soft_delete_hides_but_preserves_dependents(self):
        self.client_obj.soft_delete()

        # Hidden from the default manager, visible via all_objects.
        self.assertFalse(Client.objects.filter(pk=self.client_obj.pk).exists())
        self.assertTrue(Client.all_objects.filter(pk=self.client_obj.pk).exists())

        # The job (and thus its phases/timeslots/history) survives, and
        # job.client still resolves via the base manager.
        self.job.refresh_from_db()
        self.assertEqual(self.job.client_id, self.client_obj.pk)
        self.assertEqual(self.job.client.name, "Acme")

    def test_restore(self):
        self.client_obj.soft_delete()
        self.client_obj.restore()
        self.assertTrue(Client.objects.filter(pk=self.client_obj.pk).exists())

    def test_unit_soft_delete_preserves_job(self):
        self.unit.soft_delete()
        self.assertFalse(OrganisationalUnit.objects.filter(pk=self.unit.pk).exists())
        self.job.refresh_from_db()
        self.assertEqual(self.job.unit.name, "Unit A")


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class ClientDeleteViewTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(name="Acme")
        self.superuser = User.objects.create_superuser(
            email="admin@test.com", password="pw12345"
        )
        self.plain = User.objects.create_user(email="nobody@test.com", password="pw12345")
        # custom SessionMiddleware rejects requests without HTTP_HOST
        self.http = HttpClient(HTTP_HOST="localhost")

    def test_delete_confirm_page_renders(self):
        self.http.force_login(self.superuser)
        resp = self.http.get(
            reverse("client_delete", kwargs={"slug": self.client_obj.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Delete Client")

    def test_delete_view_soft_deletes(self):
        self.http.force_login(self.superuser)
        resp = self.http.post(
            reverse("client_delete", kwargs={"slug": self.client_obj.slug})
        )
        self.assertEqual(resp.status_code, 302)
        self.client_obj.refresh_from_db()
        self.assertTrue(self.client_obj.is_deleted)

    def test_delete_view_requires_permission(self):
        self.http.force_login(self.plain)
        resp = self.http.post(
            reverse("client_delete", kwargs={"slug": self.client_obj.slug})
        )
        self.assertEqual(resp.status_code, 403)
        self.client_obj.refresh_from_db()
        self.assertFalse(self.client_obj.is_deleted)
