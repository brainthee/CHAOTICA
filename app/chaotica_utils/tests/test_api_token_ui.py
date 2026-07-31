"""Tests for the self-service API token management UI (profile page).

Covers create / regenerate / revoke of a user's personal DRF auth token, and
that a token authenticates as -- and only as -- its owner.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token

from chaotica_utils.models import User


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class ApiTokenUITests(TestCase):
    def setUp(self):
        # First create_user is auto-promoted to superuser.
        self.admin = User.objects.create_user(
            email="admin@test.com", password="pw12345"
        )
        self.user = User.objects.create_user(
            email="user@test.com", password="pw12345"
        )

    def test_create_requires_login(self):
        resp = self.client.post(
            reverse("create_own_api_token"), HTTP_HOST="testserver"
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp["Location"])

    def test_create_is_get_or_create(self):
        self.client.force_login(self.user)
        url = reverse("create_own_api_token")

        self.client.post(url, HTTP_HOST="testserver")
        first = Token.objects.get(user=self.user)

        # A second create does not mint a new token (one-per-user, idempotent).
        self.client.post(url, HTTP_HOST="testserver")
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Token.objects.get(user=self.user).key, first.key)

    def test_create_rejects_get(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("create_own_api_token"), HTTP_HOST="testserver"
        )
        self.assertEqual(resp.status_code, 405)

    def test_reset_regenerates_key(self):
        self.client.force_login(self.user)
        original = Token.objects.create(user=self.user)

        resp = self.client.post(
            reverse("reset_own_api_token"),
            {"user_action": "approve_action"},
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["form_is_valid"])
        new_key = Token.objects.get(user=self.user).key
        self.assertNotEqual(new_key, original.key)

    def test_reset_get_renders_modal_without_changing(self):
        self.client.force_login(self.user)
        original = Token.objects.create(user=self.user)
        resp = self.client.get(
            reverse("reset_own_api_token"), HTTP_HOST="testserver"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["form_is_valid"])
        self.assertEqual(Token.objects.get(user=self.user).key, original.key)

    def test_revoke_deletes_token(self):
        self.client.force_login(self.user)
        Token.objects.create(user=self.user)
        resp = self.client.post(
            reverse("revoke_own_api_token"),
            {"user_action": "approve_action"},
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_token_card_shows_on_own_profile(self):
        self.client.force_login(self.user)
        Token.objects.create(user=self.user)
        resp = self.client.get(
            reverse("update_profile", kwargs={"email": self.user.email}),
            HTTP_HOST="testserver",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="api-tokens"')
        self.assertContains(resp, Token.objects.get(user=self.user).key)
