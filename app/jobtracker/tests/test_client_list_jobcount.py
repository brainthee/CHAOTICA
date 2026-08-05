"""The clients list exposes a (sortable) job count via the datatables API."""
from django.test import TestCase, Client as HttpClient, override_settings
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.models import Client, Job, OrganisationalUnit
from jobtracker.enums import JobStatuses


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class ClientJobCountTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@test.com", password="pw12345"
        )
        self.unit = OrganisationalUnit.objects.create(name="Unit A")
        self.client_obj = Client.objects.create(name="Acme")
        # Two live jobs + one soft-deleted job (should not be counted).
        for i in range(2):
            Job.objects.create(
                unit=self.unit, client=self.client_obj, title=f"Live {i}",
                created_by=self.superuser, account_manager=self.superuser,
            )
        Job.objects.create(
            unit=self.unit, client=self.client_obj, title="Gone",
            status=JobStatuses.DELETED,
            created_by=self.superuser, account_manager=self.superuser,
        )
        self.http = HttpClient(HTTP_HOST="localhost")

    def test_jobs_count_excludes_deleted(self):
        self.http.force_login(self.superuser)
        resp = self.http.get(reverse("client-list") + "?format=datatables")
        self.assertEqual(resp.status_code, 200)
        row = next(r for r in resp.json()["data"] if r["name"] == "Acme")
        self.assertEqual(row["jobs_count"], 2)
