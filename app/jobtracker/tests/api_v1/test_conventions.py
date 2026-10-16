"""v1 conventions (A1): refs, web_url, error envelope, filters, ordering."""

from constance.test import override_config

from jobtracker.enums import JobStatuses, PhaseStatuses
from jobtracker.models import Client, Job, Phase

from .helpers import ApiV1TestCase, make_member


class RefShapeTests(ApiV1TestCase):
    def test_job_list_renders_fks_as_refs(self):
        job = self.make_job(account_manager=self.normal)
        row = self.as_user(self.superuser).get("/api/v1/jobs/").json()["results"][0]
        self.assertEqual(row["id"], job.pk)
        self.assertEqual(row["job_id"], job.id)
        self.assertEqual(
            set(row["client"]), {"id", "type", "display", "url", "web_url"}
        )
        self.assertEqual(row["client"]["type"], "client")
        self.assertEqual(row["client"]["url"], f"/api/v1/clients/{job.client.pk}/")
        self.assertTrue(row["client"]["web_url"].startswith("http://testserver/"))
        self.assertEqual(row["account_manager"]["id"], self.normal.pk)
        self.assertTrue(row["web_url"].endswith(f"/{job.slug}/"))

    def test_list_id_fetches_the_same_job(self):
        # Job's pk (db_id) differs from its Job ID; the listed id must be the
        # one /jobs/{id}/ resolves.
        self.make_job(title="first")
        job = self.make_job(title="second")
        client = self.as_user(self.superuser)
        listed = {
            r["title"]: r["id"] for r in client.get("/api/v1/jobs/").json()["results"]
        }
        detail = client.get(f"/api/v1/jobs/{listed['second']}/").json()
        self.assertEqual(detail["job_id"], job.id)

    def test_phase_ref_display_and_client(self):
        job = self.make_job()
        phase = self.make_phase(job, title="External Infra")
        row = self.as_user(self.superuser).get("/api/v1/phases/").json()["results"][0]
        self.assertEqual(row["job"]["id"], job.pk)
        self.assertEqual(row["client"]["id"], job.client.pk)
        phase.refresh_from_db()
        self.assertEqual(
            self.as_user(self.superuser)
            .get(f"/api/v1/phases/{phase.pk}/")
            .json()["job"]["display"],
            str(job),
        )

    def test_null_fk_is_null(self):
        self.make_phase(self.make_job())
        row = self.as_user(self.superuser).get("/api/v1/phases/").json()["results"][0]
        self.assertIsNone(row["project_lead"])

    def test_slugless_object_has_no_web_url_and_is_not_saved(self):
        client = Client.objects.create(name="No Slug")
        Client.objects.filter(pk=client.pk).update(slug="")
        row = self.as_user(self.superuser).get(f"/api/v1/clients/{client.pk}/").json()
        self.assertIsNone(row["web_url"])
        client.refresh_from_db()
        self.assertEqual(client.slug, "")


class ErrorEnvelopeTests(ApiV1TestCase):
    def test_not_authenticated(self):
        body = self.client.get("/api/v1/jobs/").json()
        self.assertEqual(body["error"]["code"], "not_authenticated")
        self.assertTrue(body["error"]["message"])

    def test_not_found(self):
        resp = self.as_user(self.superuser).get("/api/v1/jobs/999999/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"]["code"], "not_found")

    def test_permission_denied(self):
        resp = self.as_user(self.normal).post(
            f"/api/v1/users/{self.superuser.pk}/set-status/", {"is_active": False}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "permission_denied")

    def test_validation_fields(self):
        resp = self.as_user(self.superuser).post(
            f"/api/v1/users/{self.normal.pk}/set-status/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        err = resp.json()["error"]
        self.assertEqual(err["code"], "invalid")
        self.assertIn("is_active", err["fields"])

    def test_bad_filter_value(self):
        resp = self.as_user(self.superuser).get("/api/v1/phases/?lead=bob")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "invalid")

    @override_config(MAINTENANCE_MODE=True)
    def test_maintenance_code(self):
        resp = self.as_user(self.normal).get("/api/v1/jobs/")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error"]["code"], "maintenance")


class FilterTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.job_a = self.make_job(title="Alpha", status=JobStatuses.SCOPING)
        self.job_b = self.make_job(
            title="Bravo", status=JobStatuses.IN_PROGRESS, account_manager=self.normal
        )
        self.lead_phase = self.make_phase(self.job_b, project_lead=self.normal)
        self.other_phase = self.make_phase(self.job_a)
        self.su = self.as_user(self.superuser)

    def test_status_in(self):
        resp = self.su.get(f"/api/v1/jobs/?status__in={JobStatuses.SCOPING}")
        self.assert_same_ids(resp, Job.objects.filter(pk=self.job_a.pk))

    def test_search_q(self):
        resp = self.su.get("/api/v1/jobs/?q=bravo")
        self.assert_same_ids(resp, Job.objects.filter(pk=self.job_b.pk))

    def test_lead_me(self):
        resp = self.as_user(self.normal).get("/api/v1/phases/?lead=me")
        # normal can see the phase they lead via the team bypass.
        self.assert_same_ids(resp, Phase.objects.filter(pk=self.lead_phase.pk))

    def test_involving_me_on_jobs(self):
        resp = self.as_user(self.normal).get("/api/v1/jobs/?involving=me")
        self.assert_same_ids(resp, Job.objects.filter(pk=self.job_b.pk))

    def test_phase_job_filter(self):
        resp = self.su.get(f"/api/v1/phases/?job={self.job_a.pk}")
        self.assert_same_ids(resp, Phase.objects.filter(pk=self.other_phase.pk))

    def test_ordering_allowlist(self):
        ordered = self.su.get("/api/v1/jobs/?ordering=-title").json()["results"]
        self.assertEqual([r["title"] for r in ordered], ["Bravo", "Alpha"])
        # Not in the allowlist: ignored rather than honoured.
        resp = self.su.get("/api/v1/jobs/?ordering=overview")
        self.assertEqual(resp.status_code, 200)

    def test_filters_never_widen(self):
        # normal sees nothing via unit perms; filters can't add rows.
        resp = self.as_user(self.normal).get(f"/api/v1/phases/?job={self.job_a.pk}")
        self.assertEqual(resp.json()["count"], 0)


class UnitScopedListTests(ApiV1TestCase):
    def test_unit_member_sees_unit_jobs(self):
        job = self.make_job()
        self.make_job()  # another unit
        viewer = make_member(self.normal, job.unit, roles=("Consultant",))
        resp = self.as_user(viewer).get("/api/v1/jobs/")
        self.assert_same_ids(resp, Job.objects.filter(pk=job.pk))
        resp = self.as_user(viewer).get(
            f"/api/v1/phases/?status__in={PhaseStatuses.DRAFT}"
        )
        self.assertEqual(resp.status_code, 200)
