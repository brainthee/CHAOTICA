"""Delete affordances for the config/reference models (Service, Contact, ...).

Covers the confirm page rendering and, importantly, that deleting a client
contact now requires delete_contact (it previously inherited view_contact).
"""
from django.test import TestCase, Client as HttpClient, override_settings
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.models import Client, Contact, Service


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class ConfigDeleteUITests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@test.com", password="pw12345"
        )
        self.plain = User.objects.create_user(email="nobody@test.com", password="pw12345")
        self.service = Service.objects.create(name="Web App Test")
        self.client_obj = Client.objects.create(name="Acme")
        self.contact = Contact.objects.create(company=self.client_obj, first_name="Pat")
        self.http = HttpClient(HTTP_HOST="localhost")

    def test_service_delete_confirm_renders(self):
        self.http.force_login(self.superuser)
        resp = self.http.get(reverse("service_delete", kwargs={"slug": self.service.slug}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Delete Service")

    def test_service_delete_redirects_to_list_not_detail(self):
        self.http.force_login(self.superuser)
        resp = self.http.post(reverse("service_delete", kwargs={"slug": self.service.slug}))
        self.assertEqual(resp.status_code, 302)
        # Must not redirect to the deleted service's own detail page (404).
        self.assertEqual(resp.url, reverse("service_list"))

    def test_contact_delete_requires_delete_permission(self):
        # A user with only view rights must not be able to delete a contact.
        self.http.force_login(self.plain)
        resp = self.http.post(
            reverse(
                "client_contact_delete",
                kwargs={"client_slug": self.client_obj.slug, "pk": self.contact.pk},
            )
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Contact.objects.filter(pk=self.contact.pk).exists())

    def test_contact_delete_works_for_superuser(self):
        self.http.force_login(self.superuser)
        resp = self.http.post(
            reverse(
                "client_contact_delete",
                kwargs={"client_slug": self.client_obj.slug, "pk": self.contact.pk},
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())
