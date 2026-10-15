from django.core.cache import cache
from django.test import Client as TestHttpClient, TestCase
from django.urls import reverse
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User
from jobtracker.enums import PhaseStatuses
from jobtracker.models import Client, Job, OrganisationalUnit, Phase, Service


class ServicePhaseBucketTests(TestCase):
    """Service page Active / Upcoming / Completed tabs (T-06)."""

    def setUp(self):
        cache.clear()
        # First user is promoted to admin; keep it out of the way.
        self.root = User.objects.create_user(email="root@svc.com", password="pw")
        self.viewer = User.objects.create_user(email="view@svc.com", password="pw")
        self.viewer.is_superuser = False
        self.viewer.save()
        self.service = Service.objects.create(name="Network Device Review")
        assign_perm("jobtracker.view_service", self.viewer)

        self.unit = OrganisationalUnit.objects.create(name="Svc Unit")
        client = Client.objects.create(name="Svc Client")
        self.seen_job = Job.objects.create(
            title="Seen", unit=self.unit, client=client,
            created_by=self.root, account_manager=self.root,
        )
        self.hidden_job = Job.objects.create(
            title="Hidden", unit=self.unit, client=client,
            created_by=self.root, account_manager=self.root,
        )
        assign_perm("jobtracker.view_job", self.viewer, self.seen_job)

        self.phases = {}
        for name, status in [
            ("upcoming", PhaseStatuses.SCHEDULED_CONFIRMED),
            ("active", PhaseStatuses.QA_TECH),
            ("completed", PhaseStatuses.DELIVERED),
            ("cancelled", PhaseStatuses.CANCELLED),
        ]:
            self.phases[name] = Phase.objects.create(
                job=self.seen_job, title="Seen " + name, status=status,
                service=self.service,
            )
        self.hidden = Phase.objects.create(
            job=self.hidden_job, title="Secret phase", status=PhaseStatuses.QA_TECH,
            service=self.service,
        )
        self.http = TestHttpClient(HTTP_HOST="localhost")
        self.http.force_login(self.viewer)

    def _bucket(self, bucket):
        url = reverse(
            "service_phases_partial",
            kwargs={"slug": self.service.slug, "bucket": bucket},
        )
        resp = self.http.get(url)
        self.assertEqual(resp.status_code, 200)
        return resp.json()["html"]

    def test_groups_do_not_overlap_and_skip_closed(self):
        groups = [
            set(PhaseStatuses.SERVICE_UPCOMING),
            set(PhaseStatuses.SERVICE_ACTIVE),
            set(PhaseStatuses.SERVICE_COMPLETED),
        ]
        for i, a in enumerate(groups):
            for b in groups[i + 1:]:
                self.assertFalse(a & b)
        closed = {PhaseStatuses.CANCELLED, PhaseStatuses.POSTPONED, PhaseStatuses.DELETED}
        self.assertFalse(closed & set().union(*groups))

    def test_each_bucket_lists_its_phases_only(self):
        for bucket in ("upcoming", "active", "completed"):
            html = self._bucket(bucket)
            for name in ("upcoming", "active", "completed", "cancelled"):
                title = "Seen " + name
                if name == bucket:
                    self.assertIn(title, html, bucket)
                else:
                    self.assertNotIn(title, html, bucket)
        self.assertIn("Seen cancelled", self._bucket("all"))

    def test_hidden_job_phases_not_listed_or_counted(self):
        for bucket in ("active", "all"):
            self.assertNotIn("Secret phase", self._bucket(bucket))
        resp = self.http.get(
            reverse("service_detail", kwargs={"slug": self.service.slug})
        )
        self.assertEqual(resp.status_code, 200)
        analytics = resp.context["analytics"]
        self.assertEqual(analytics["active_count"], 1)
        self.assertEqual(analytics["upcoming_count"], 1)
        self.assertEqual(analytics["completed_count"], 1)
        self.assertEqual(analytics["total_phases"], 4)
        self.assertContains(
            resp,
            reverse(
                "service_phases_partial",
                kwargs={"slug": self.service.slug, "bucket": "active"},
            ),
        )

    def test_counts_refresh_when_a_phase_changes(self):
        url = reverse("service_detail", kwargs={"slug": self.service.slug})
        self.assertEqual(self.http.get(url).context["analytics"]["active_count"], 1)
        phase = self.phases["upcoming"]
        phase.status = PhaseStatuses.IN_PROGRESS
        phase.save()
        self.assertEqual(self.http.get(url).context["analytics"]["active_count"], 2)

    def test_requires_view_service_and_known_bucket(self):
        url = reverse(
            "service_phases_partial",
            kwargs={"slug": self.service.slug, "bucket": "bogus"},
        )
        self.assertEqual(self.http.get(url).status_code, 404)
        stranger = User.objects.create_user(email="no@svc.com", password="pw")
        self.http.force_login(stranger)
        url = reverse(
            "service_phases_partial",
            kwargs={"slug": self.service.slug, "bucket": "active"},
        )
        self.assertEqual(self.http.get(url).status_code, 403)
