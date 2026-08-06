"""AjaxLoginRedirect401Middleware: an expired session on an AJAX request should
surface as a 401 JSON body rather than a 302 to the login page (which a browser
follows transparently, handing the front-end login HTML with a 200 status)."""

from django.test import TestCase, Client, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class AjaxLoginRedirect401Tests(TestCase):
    def setUp(self):
        # Custom SessionMiddleware rejects requests without a Host header.
        self.client = Client(HTTP_HOST="localhost")
        self.url = reverse("view_scheduler")  # a @login_required view

    def test_normal_request_redirects_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.headers.get("Location", ""))

    def test_ajax_request_gets_401_json(self):
        resp = self.client.get(self.url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.headers.get("Content-Type"), "application/json")
        self.assertIn("error", resp.json())
