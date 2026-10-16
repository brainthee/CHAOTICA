"""Site middleware vs /api/v1/ users (A0).

Token / OAuth2 callers authenticate inside the DRF view, after the site
middleware has run, so anything middleware decides from ``request.user`` must
either be deferred (maintenance) or read lazily (audit actor).
"""

from constance.test import override_config
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from chaotica_utils.middleware.common import get_current_user
from chaotica_utils.models import AuditEvent, User
from jobtracker.models import TimeSlot

from .helpers import ApiV1TestCase

PROBE = "/api/v1/_probe/"


@override_settings(ROOT_URLCONF="jobtracker.tests.api_v1.urls")
class MaintenanceModeTests(ApiV1TestCase):
    @override_config(MAINTENANCE_MODE=True)
    def test_token_user_gets_json_503_not_redirect(self):
        resp = self.token_client(self.normal).get("/api/v1/users/")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["detail"].split()[0], "CHAOTICA")

    @override_config(MAINTENANCE_MODE=True)
    def test_superuser_token_passes(self):
        resp = self.token_client(self.superuser).get("/api/v1/users/")
        self.assertEqual(resp.status_code, 200)

    @override_config(MAINTENANCE_MODE=True)
    def test_schema_and_token_endpoints_503(self):
        client = self.token_client(self.normal)
        self.assertEqual(client.get("/api/v1/schema/").status_code, 503)
        resp = self.client.post(
            "/api/v1/auth/token/",
            {"username": "normal@example.com", "password": "pw-normal"},
        )
        self.assertEqual(resp.status_code, 503)

    @override_config(MAINTENANCE_MODE=True)
    def test_legacy_api_still_redirects(self):
        self.client.force_login(self.normal)
        resp = self.client.get("/api/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("maintenance"))


class SetupRequiredTests(ApiV1TestCase):
    def test_api_gets_json_503_while_setup_needed(self):
        # The deleted-account placeholder means the user table is never empty
        # in tests; seed the middleware's cached answer instead.
        cache.set("chaotica_setup_needed", True, 60)
        resp = self.client.get("/api/v1/users/")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error"]["code"], "setup_required")


@override_settings(ROOT_URLCONF="jobtracker.tests.api_v1.urls")
class AuditAttributionTests(ApiV1TestCase):
    def _slot_events(self, slot):
        # Non-delivery slots audit against their owning user.
        return AuditEvent.objects.filter(
            target_content_type=ContentType.objects.get_for_model(User),
            target_id=str(slot.user_id),
        )

    def test_token_user_is_actor_and_history_user(self):
        resp = self.token_client(self.normal).post(PROBE)
        self.assertEqual(resp.status_code, 200)
        slot = TimeSlot.objects.get(pk=resp.json()["id"])
        event = self._slot_events(slot).latest("pk")
        self.assertEqual(event.actor, self.normal)
        self.assertEqual(slot.history.latest().history_user, self.normal)

    def test_session_user_is_actor(self):
        self.client.force_login(self.normal)
        resp = self.client.post(PROBE)
        slot = TimeSlot.objects.get(pk=resp.json()["id"])
        self.assertEqual(self._slot_events(slot).latest("pk").actor, self.normal)
        self.assertEqual(slot.history.latest().history_user, self.normal)

    def test_impersonation_records_real_user(self):
        self.client.force_login(self.superuser)
        self.client.get(reverse("impersonate-start", args=[self.normal.pk]))
        resp = self.client.post(PROBE)
        slot = TimeSlot.objects.get(pk=resp.json()["id"])
        self.assertEqual(slot.user, self.normal)
        event = self._slot_events(slot).latest("pk")
        self.assertEqual(event.actor, self.normal)
        self.assertEqual(event.metadata["impersonator_id"], self.superuser.pk)

    def test_current_user_cleared_after_request(self):
        self.token_client(self.normal).get(PROBE)
        self.assertIsNone(get_current_user())


@override_settings(ROOT_URLCONF="jobtracker.tests.api_v1.urls")
class TimezoneTests(ApiV1TestCase):
    def test_output_is_utc_for_session_user_with_timezone(self):
        self.normal.pref_timezone = "Asia/Tokyo"
        self.normal.save()
        self.client.force_login(self.normal)
        data = self.client.get(PROBE).json()
        self.assertEqual(data["tz"], "UTC")
        self.assertTrue(data["now"].endswith("Z") or data["now"].endswith("+00:00"))

    def test_output_is_utc_for_token_user(self):
        self.assertEqual(self.token_client(self.normal).get(PROBE).json()["tz"], "UTC")


class TokenEndpointTests(ApiV1TestCase):
    URL = "/api/v1/auth/token/"
    CREDS = {"username": "normal@example.com", "password": "pw-normal"}

    def test_issues_token(self):
        resp = self.client.post(self.URL, self.CREDS)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.json())

    @override_config(LOCAL_LOGIN_ENABLED=False)
    def test_refused_when_local_login_disabled(self):
        self.assertEqual(self.client.post(self.URL, self.CREDS).status_code, 403)

    def test_throttled_after_ten_calls(self):
        for _ in range(10):
            self.assertNotEqual(self.client.post(self.URL, self.CREDS).status_code, 429)
        self.assertEqual(self.client.post(self.URL, self.CREDS).status_code, 429)

    def test_spoofed_forwarded_for_does_not_reset_throttle(self):
        # The proxy appends the real client address; whatever the client put
        # in front of it must not change the throttle key.
        for i in range(11):
            resp = self.client.post(
                self.URL,
                self.CREDS,
                HTTP_X_FORWARDED_FOR=f"203.0.113.{i}, 198.51.100.7",
            )
        self.assertEqual(resp.status_code, 429)


@override_settings(CORS_ALLOWED_ORIGINS=["https://lcars.example.com"])
class CorsTests(ApiV1TestCase):
    def _preflight(self, path, origin):
        return self.client.options(
            path,
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )

    def test_listed_origin_allowed_without_credentials(self):
        resp = self._preflight("/api/v1/users/", "https://lcars.example.com")
        self.assertEqual(
            resp.get("access-control-allow-origin"), "https://lcars.example.com"
        )
        self.assertIsNone(resp.get("access-control-allow-credentials"))

    def test_other_origin_refused(self):
        resp = self._preflight("/api/v1/users/", "https://evil.example.com")
        self.assertIsNone(resp.get("access-control-allow-origin"))

    def test_non_api_paths_never_cors(self):
        resp = self._preflight("/api/", "https://lcars.example.com")
        self.assertIsNone(resp.get("access-control-allow-origin"))


class ScheduleSchemaTests(ApiV1TestCase):
    def test_schedule_documented_as_single_object(self):
        from drf_spectacular.generators import SchemaGenerator

        schema = SchemaGenerator().get_schema(request=None, public=True)
        path = next(p for p in schema["paths"] if p.endswith("/schedule/") and "{" not in p)
        op = schema["paths"][path]["get"]
        body = op["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertNotEqual(body.get("type"), "array")
        self.assertIn("$ref", body)

