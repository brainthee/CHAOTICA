"""Platform endpoints (A2): /meta/, /me/, /me/preferences/, /me/schedule/, /search/."""

from constance.test import override_config
from django.conf import settings
from django.urls import reverse

from chaotica_utils.selectors.search import site_search
from chaotica_utils.models import Group, User

from .helpers import ApiV1TestCase, make_member


class MetaTests(ApiV1TestCase):
    def test_public_and_hides_version(self):
        resp = self.client.get("/api/v1/meta/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body["version"])
        self.assertEqual(body["api_version"], "1")
        self.assertTrue(body["ws_url"].startswith("ws://testserver/"))
        self.assertIn("entropy_meter", body["features"])
        self.assertTrue(body["auth"]["login_url"].startswith("http://testserver/"))

    def test_version_for_signed_in(self):
        body = self.as_user(self.normal).get("/api/v1/meta/").json()
        self.assertEqual(body["version"], settings.DJANGO_VERSION)

    @override_config(MAINTENANCE_MODE=True)
    def test_answers_during_maintenance(self):
        body = self.client.get("/api/v1/meta/").json()
        self.assertTrue(body["maintenance"])

    @override_config(LOCAL_LOGIN_ENABLED=False)
    def test_no_token_url_without_local_login(self):
        self.assertIsNone(self.client.get("/api/v1/meta/").json()["auth"]["token_url"])


class MeTests(ApiV1TestCase):
    def test_profile(self):
        boss = User.objects.create_user(email="boss@example.com", password="pw")
        self.normal.manager = boss
        self.normal.pref_timezone = "Europe/London"
        self.normal.save()
        job = self.make_job()
        me_user = make_member(self.normal, job.unit, roles=("Consultant",))
        group, _ = Group.objects.get_or_create(
            name=settings.GLOBAL_GROUP_PREFIX + "User"
        )
        me_user.groups.add(group)

        body = self.as_user(me_user).get("/api/v1/me/").json()
        self.assertEqual(body["id"], me_user.pk)
        self.assertEqual(body["tz"], "Europe/London")
        self.assertEqual(body["manager"]["id"], boss.pk)
        self.assertIsNone(body["acting_manager"])
        self.assertEqual(body["units"][0]["unit"]["id"], job.unit.pk)
        self.assertEqual(body["units"][0]["roles"], ["Consultant"])
        self.assertIn("User", body["global_roles"])
        self.assertTrue(body["avatar_url"].startswith("http://testserver/"))
        self.assertFalse(body["capabilities"]["is_global_admin"])
        self.assertIsInstance(body["capabilities"]["can_scope"], bool)

    def test_query_budget(self):
        client = self.as_user(self.normal)
        client.get("/api/v1/me/")  # warm content-type / constance caches
        with self.assertNumQueries(14):
            client.get("/api/v1/me/")

    def test_preferences(self):
        body = self.as_user(self.normal).get("/api/v1/me/preferences/").json()
        self.assertEqual(
            set(body), {"theme", "tz", "show_help", "scheduler_default_filter"}
        )

    def test_me_schedule_is_my_user_schedule(self):
        client = self.as_user(self.normal)
        mine = client.get("/api/v1/me/schedule/?start=2026-01-05&end=2026-01-09").json()
        theirs = client.get(
            f"/api/v1/users/{self.normal.pk}/schedule/?start=2026-01-05&end=2026-01-09"
        ).json()
        self.assertEqual(mine, theirs)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)


class SearchTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.job = self.make_job(title="Daystrom Pentest")
        self.phase = self.make_phase(self.job, title="Daystrom Web")
        self.hidden = self.make_job(title="Daystrom Secret")
        self.viewer = make_member(
            User.objects.create_user(
                email="v@example.com", password="pw", first_name="Daystrom"
            ),
            self.job.unit,
        )

    def _groups(self, client, q):
        body = client.get("/api/v1/search/", {"q": q, "limit": 50}).json()
        return {g["type"]: {r["id"] for r in g["results"]} for g in body["groups"]}

    def test_scoped_like_the_header_search(self):
        groups = self._groups(self.as_user(self.viewer), "daystrom")
        self.assertEqual(groups["jobs"], {self.job.pk})
        self.assertEqual(groups["phases"], {self.phase.pk})
        expected = site_search(self.viewer, "daystrom", limit=50)
        self.assertEqual(groups["jobs"], {j.pk for j in expected["jobs"]})

    def test_users_are_identity_refs(self):
        body = (
            self.as_user(self.viewer).get("/api/v1/search/", {"q": "daystrom"}).json()
        )
        people = next(g for g in body["groups"] if g["type"] == "users")
        self.assertEqual(
            set(people["results"][0]), {"id", "type", "display", "url", "web_url"}
        )

    def test_short_query_returns_nothing(self):
        body = self.as_user(self.viewer).get("/api/v1/search/", {"q": "da"}).json()
        self.assertEqual(body["groups"], [])

    def test_no_billing_codes_group(self):
        body = (
            self.as_user(self.superuser)
            .get("/api/v1/search/", {"q": "daystrom"})
            .json()
        )
        self.assertNotIn("billing_codes", {g["type"] for g in body["groups"]})

    def test_goto(self):
        client = self.as_user(self.viewer)
        resp = client.get("/api/v1/search/goto/", {"id": str(self.job.id)})
        self.assertEqual(resp.json()["id"], self.job.pk)
        self.phase.refresh_from_db()
        resp = client.get("/api/v1/search/goto/", {"id": self.phase.phase_id})
        self.assertEqual(resp.json()["type"], "phase")
        resp = client.get("/api/v1/search/goto/", {"id": str(self.hidden.id)})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"]["code"], "not_found")

    def test_header_search_still_renders(self):
        self.client.force_login(self.viewer)
        resp = self.client.post(
            reverse("search"), {"q": "daystrom"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(resp.status_code, 200, resp.content[:200])
        self.assertIn("Daystrom Pentest", resp.json()["html_form"])
        self.assertNotIn("Daystrom Secret", resp.json()["html_form"])
