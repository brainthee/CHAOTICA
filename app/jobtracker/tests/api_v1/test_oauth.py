"""OAuth2 sign-in, Connected Apps and realtime tickets (A8)."""

import base64
import hashlib
import secrets
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from constance.test import override_config
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, get_application_model

from chaotica_utils.models import AuditEvent, AuditVerb, User
from chaotica_utils.realtime import issue_ticket, redeem_ticket
from notifications.models import Notification

from .helpers import ApiV1TestCase

Application = get_application_model()
REDIRECT = "https://lcars.example.com/callback"
ORIGIN = "https://lcars.example.com"
IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


@override_config(API_OAUTH2_ENABLED=True)
class OAuthBase(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.app = Application.objects.create(
            name="LCARS",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=REDIRECT,
            allowed_origins=ORIGIN,
            client_secret="",
            user=self.superuser,
        )

    def _authorize(self, user, challenge, method="S256", **extra):
        self.client.force_login(user)
        params = {
            "response_type": "code",
            "client_id": self.app.client_id,
            "redirect_uri": REDIRECT,
            "scope": "read",
            "state": "xyz",
            **extra,
        }
        if challenge is not None:
            params.update(code_challenge=challenge, code_challenge_method=method)
        return params, self.client.get("/o/authorize/", params)

    def _code(self, user, challenge):
        params, _resp = self._authorize(user, challenge)
        resp = self.client.post("/o/authorize/", {**params, "allow": "Allow"})
        self.assertEqual(resp.status_code, 302, resp.content[:300])
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["state"], ["xyz"])
        return query["code"][0]

    def _token(self, **data):
        return self.client.post(
            "/o/token/",
            {"client_id": self.app.client_id, "redirect_uri": REDIRECT, **data},
        )

    def _sign_in(self, user=None):
        user = user or self.normal
        verifier, challenge = _pkce()
        code = self._code(user, challenge)
        resp = self._token(
            grant_type="authorization_code", code=code, code_verifier=verifier
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.client.logout()
        return resp.json()


class AuthorizationCodeFlowTests(OAuthBase):
    def test_full_flow_and_bearer_call(self):
        tokens = self._sign_in()
        self.assertIn("refresh_token", tokens)
        self.assertEqual(tokens["scope"], "read")
        api = self.as_bearer(tokens["access_token"])
        body = api.get("/api/v1/me/").json()
        self.assertEqual(body["id"], self.normal.pk)

    def test_consent_page_renders_and_iss_returned(self):
        verifier, challenge = _pkce()
        params, resp = self._authorize(self.normal, challenge)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Connect LCARS?")
        resp = self.client.post("/o/authorize/", {**params, "allow": "Allow"})
        self.assertIn("iss", parse_qs(urlsplit(resp["Location"]).query))

    def test_pkce_required(self):
        _params, resp = self._authorize(self.normal, None)
        self.assertIn(resp.status_code, (302, 400))
        if resp.status_code == 302:
            self.assertIn("error=", resp["Location"])
            self.assertNotIn("code=", resp["Location"])

    def test_plain_pkce_rejected(self):
        params, _resp = self._authorize(
            self.normal, "plain-challenge-" + "x" * 40, method="plain"
        )
        resp = self.client.post("/o/authorize/", {**params, "allow": "Allow"})
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["error"], ["invalid_request"])
        self.assertNotIn("code", query)

    def test_wrong_verifier_rejected(self):
        _verifier, challenge = _pkce()
        code = self._code(self.normal, challenge)
        resp = self._token(
            grant_type="authorization_code", code=code, code_verifier="x" * 50
        )
        self.assertEqual(resp.status_code, 400)

    def test_password_grant_rejected(self):
        resp = self._token(
            grant_type="password", username="normal@example.com", password="pw-normal"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("access_token", resp.json())

    def test_unregistered_redirect_rejected(self):
        _verifier, challenge = _pkce()
        _params, resp = self._authorize(
            self.normal, challenge, redirect_uri="https://evil.example.net/cb"
        )
        self.assertEqual(resp.status_code, 400)

    def test_refresh_rotates_and_reuse_is_refused(self):
        tokens = self._sign_in()
        first = self._token(
            grant_type="refresh_token", refresh_token=tokens["refresh_token"]
        )
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.json()["refresh_token"], tokens["refresh_token"])
        reused = self._token(
            grant_type="refresh_token", refresh_token=tokens["refresh_token"]
        )
        self.assertEqual(reused.status_code, 400)


class BearerRulesTests(OAuthBase):
    def _token_for(self, user, scope="read"):
        raw = secrets.token_urlsafe(30)
        AccessToken.objects.create(
            user=user,
            application=self.app,
            token=raw,
            scope=scope,
            expires=timezone.now() + timedelta(hours=1),
        )
        return raw

    def test_scope_needed(self):
        api = self.as_bearer(self._token_for(self.normal, scope="write"))
        resp = api.get("/api/v1/me/")
        self.assertEqual(resp.status_code, 403)

    def test_inactive_user_refused(self):
        raw = self._token_for(self.normal)
        User.objects.filter(pk=self.normal.pk).update(is_active=False)
        self.assertEqual(self.as_bearer(raw).get("/api/v1/me/").status_code, 401)

    def test_deactivation_revokes(self):
        raw = self._token_for(self.normal)
        user = User.objects.get(pk=self.normal.pk)
        user.set_active_status(False)
        self.assertFalse(AccessToken.objects.filter(user=user).exists())
        user.set_active_status(True)
        self.assertEqual(self.as_bearer(raw).get("/api/v1/me/").status_code, 401)

    def test_session_and_drf_token_unaffected(self):
        self.assertEqual(self.as_user(self.normal).get("/api/v1/me/").status_code, 200)
        self.assertEqual(
            self.token_client(self.normal).get("/api/v1/me/").status_code, 200
        )

    @override_config(API_OAUTH2_ENABLED=False)
    def test_switched_off(self):
        raw = self._token_for(self.normal)
        self.assertEqual(self.as_bearer(raw).get("/api/v1/me/").status_code, 401)
        self.client.force_login(self.normal)
        self.assertEqual(self.client.get("/o/authorize/").status_code, 404)

    def test_no_authorizing_while_impersonating(self):
        self.client.force_login(self.superuser)
        self.client.get(reverse("impersonate-start", args=[self.normal.pk]))
        self.assertEqual(self.client.get("/o/authorize/").status_code, 403)

    @override_config(MAINTENANCE_MODE=True)
    def test_token_endpoint_json_in_maintenance(self):
        resp = self._token(grant_type="refresh_token", refresh_token="x")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error"], "temporarily_unavailable")

    def test_meta_advertises_oauth(self):
        oauth = self.client.get("/api/v1/meta/").json()["auth"]["oauth"]
        self.assertTrue(oauth["authorize_url"].endswith("/o/authorize/"))
        self.assertEqual(oauth["pkce"], "S256")


class CorsTests(OAuthBase):
    def _preflight(self, path, origin=ORIGIN):
        return self.client.options(
            path, HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET"
        )

    def test_registered_origin_on_api_and_token(self):
        for path in ("/api/v1/me/", "/o/token/"):
            resp = self._preflight(path)
            self.assertEqual(resp.get("access-control-allow-origin"), ORIGIN, path)
            self.assertIsNone(resp.get("access-control-allow-credentials"))

    def test_never_on_authorize_or_pages(self):
        for path in ("/o/authorize/", "/dashboard/"):
            self.assertIsNone(
                self._preflight(path).get("access-control-allow-origin"), path
            )

    def test_unregistered_origin(self):
        resp = self._preflight("/api/v1/me/", origin="https://evil.example.net")
        self.assertIsNone(resp.get("access-control-allow-origin"))

    def test_origin_list_follows_app_changes(self):
        self.app.allowed_origins = "https://other.example.com"
        self.app.save()
        self.assertIsNone(
            self._preflight("/api/v1/me/").get("access-control-allow-origin")
        )


class ConnectedAppsUiTests(OAuthBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def test_register_app(self):
        resp = self.client.post(
            reverse("connected_app_create"),
            {
                "name": "Other",
                "redirect_uris": "https://other.example.com/cb",
                "allowed_origins": "",
            },
        )
        self.assertTrue(resp.json()["form_is_valid"], resp.json())
        app = Application.objects.get(name="Other")
        self.assertEqual(app.client_type, Application.CLIENT_PUBLIC)
        self.assertEqual(
            app.authorization_grant_type, Application.GRANT_AUTHORIZATION_CODE
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                target_repr__icontains="Other", verb="create"
            ).exists()
        )

    def test_rejects_bad_uris(self):
        for uris in (
            "ftp://x.example.com/cb",
            "https://x.example.com/cb#frag",
            "/relative",
        ):
            resp = self.client.post(
                reverse("connected_app_create"), {"name": "Bad", "redirect_uris": uris}
            )
            self.assertFalse(resp.json()["form_is_valid"], uris)
        resp = self.client.post(
            reverse("connected_app_create"),
            {
                "name": "Bad",
                "redirect_uris": REDIRECT,
                "allowed_origins": "https://x.com/path",
            },
        )
        self.assertFalse(resp.json()["form_is_valid"])

    def test_settings_page_lists_apps(self):
        resp = self.client.get(reverse("app_settings"))
        self.assertContains(resp, self.app.client_id)

    def test_needs_settings_permission(self):
        self.client.force_login(self.normal)
        self.assertEqual(
            self.client.get(reverse("connected_app_create")).status_code, 403
        )

    def test_disconnect_from_profile(self):
        tokens = self._sign_in(self.superuser)
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("update_own_profile"), follow=True)
        self.assertContains(page, "LCARS")
        resp = self.client.post(
            reverse("revoke_own_connected_app", args=[self.app.pk]),
            {"user_action": "approve_action"},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertFalse(AccessToken.objects.filter(user=self.normal).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                verb=AuditVerb.TOKEN_REVOKED, actor=self.superuser
            ).exists()
        )
        self.assertEqual(
            self.as_bearer(tokens["access_token"]).get("/api/v1/me/").status_code, 401
        )


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
# channels' database_sync_to_async closes "old" connections, which would close
# the test transaction's own connection when run on this thread.
@mock.patch("channels.db.close_old_connections", lambda: None)
class RealtimeTests(OAuthBase):
    def test_ticket_single_use(self):
        raw = issue_ticket(self.normal)
        self.assertEqual(redeem_ticket(raw), self.normal.pk)
        self.assertIsNone(redeem_ticket(raw))
        self.assertIsNone(redeem_ticket("nope"))

    def test_ticket_endpoint(self):
        body = self.as_user(self.normal).post("/api/v1/realtime/ticket/").json()
        self.assertEqual(body["expires_in"], 30)
        self.assertEqual(redeem_ticket(body["ticket"]), self.normal.pk)

    def test_me_socket_with_ticket(self):
        from chaotica.asgi import application

        Notification.objects.create(user=self.normal, title="t", message="m")
        raw = issue_ticket(self.normal)

        async def run():
            comm = WebsocketCommunicator(
                application,
                f"/ws/me/?ticket={raw}",
                headers=[
                    (b"host", b"testserver"),
                    (b"origin", b"https://elsewhere.example"),
                ],
            )
            connected, _ = await comm.connect()
            first = await comm.receive_json_from() if connected else None
            await comm.disconnect()
            again = WebsocketCommunicator(application, f"/ws/me/?ticket={raw}")
            reused, _ = await again.connect()
            return connected, first, reused

        # async_to_sync keeps database_sync_to_async on this thread, inside the
        # test transaction.
        connected, first, reused = async_to_sync(run)()
        self.assertTrue(connected)
        self.assertEqual(first, {"type": "unread", "count": 1})
        self.assertFalse(reused)

    def test_notification_push_after_commit(self):
        from notifications.utils import AppNotification, send_notifications
        from notifications.enums import NotificationTypes

        with mock.patch("chaotica_utils.realtime.push_unread_changed") as push:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                send_notifications(
                    AppNotification(
                        NotificationTypes.SYSTEM, "Hi", "There", "email/base.html"
                    ),
                    specific_users=self.normal,
                )
            push.assert_not_called()
            for cb in callbacks:
                cb()
            push.assert_called_once_with([self.normal.pk])


class SchemaTests(ApiV1TestCase):
    def test_oauth2_scheme_documented(self):
        from drf_spectacular.generators import SchemaGenerator

        schema = SchemaGenerator().get_schema(request=None, public=True)
        flow = schema["components"]["securitySchemes"]["oauth2"]["flows"][
            "authorizationCode"
        ]
        self.assertEqual(flow["tokenUrl"], "/o/token/")
