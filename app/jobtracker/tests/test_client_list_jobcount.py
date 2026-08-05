"""The clients list exposes a (sortable) job count via the datatables API."""
from django.test import TestCase, Client as HttpClient, override_settings
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.models import Client, Job, OrganisationalUnit, Project
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
        # Three projects — a different count from jobs, so a JOIN fan-out
        # (missing distinct=True) would give the wrong number for both.
        for i in range(3):
            Project.objects.create(
                title=f"Proj {i}", client=self.client_obj, created_by=self.superuser
            )
        self.http = HttpClient(HTTP_HOST="localhost")

    def _row(self):
        resp = self.http.get(reverse("client-list") + "?format=datatables")
        self.assertEqual(resp.status_code, 200)
        return next(r for r in resp.json()["data"] if r["name"] == "Acme")

    def test_jobs_count_excludes_deleted(self):
        self.http.force_login(self.superuser)
        self.assertEqual(self._row()["jobs_count"], 2)

    def test_projects_count(self):
        self.http.force_login(self.superuser)
        self.assertEqual(self._row()["projects_count"], 3)
