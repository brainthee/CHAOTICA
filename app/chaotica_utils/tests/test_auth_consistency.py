"""Verify the consistent auth story across the permission entry points:
unauthenticated users are redirected to the login page; authenticated-but-
unauthorised users get a 403. Covers the central helper, both custom decorators,
the guardian drop-in decorator, and a guardian-based CBV end-to-end.
"""
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.urls import reverse

from chaotica_utils.models import User
from chaotica_utils.decorators import superuser_required, permission_required_or_403
from jobtracker.utils import get_unit_40x_or_None


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class AuthConsistencyTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        # create_user makes the first user a superuser; the second is a normal user.
        self.superuser = User.objects.create_user(email="su@test.com", password="pw12345")
        self.user = User.objects.create_user(email="u@test.com", password="pw12345")

    def _req(self, user):
        req = self.rf.get("/somewhere/")
        req.user = user
        return req

    # --- central helper (backs unit_/job_permission_required_or_403 + mixins) ---

    def test_helper_anonymous_redirects_to_login(self):
        resp = get_unit_40x_or_None(
            self._req(AnonymousUser()), perms=["jobtracker.can_view_jobs"], return_403=True
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_helper_authenticated_unauthorised_gets_403(self):
        resp = get_unit_40x_or_None(
            self._req(self.user), perms=["jobtracker.can_view_jobs"], return_403=True
        )
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 403)

    def test_helper_authorised_passes(self):
        resp = get_unit_40x_or_None(
            self._req(self.superuser), perms=["jobtracker.can_view_jobs"], return_403=True
        )
        self.assertIsNone(resp)

    # --- superuser_required ---

    def test_superuser_required_anonymous_redirects(self):
        view = superuser_required(lambda r: HttpResponse("ok"))
        resp = view(self._req(AnonymousUser()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_superuser_required_authed_nonsuperuser_403(self):
        view = superuser_required(lambda r: HttpResponse("ok"))
        resp = view(self._req(self.user))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_required_superuser_passes(self):
        view = superuser_required(lambda r: HttpResponse("ok"))
        resp = view(self._req(self.superuser))
        self.assertEqual(resp.status_code, 200)

    # --- guardian drop-in decorator (chaotica_utils.decorators) ---

    def test_perm_decorator_anonymous_redirects(self):
        view = permission_required_or_403("chaotica_utils.manage_user")(
            lambda r: HttpResponse("ok")
        )
        resp = view(self._req(AnonymousUser()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_perm_decorator_authed_unauthorised_403(self):
        view = permission_required_or_403("chaotica_utils.manage_user")(
            lambda r: HttpResponse("ok")
        )
        resp = view(self._req(self.user))
        self.assertEqual(resp.status_code, 403)

    # --- guardian-based CBV end-to-end (SecurePermissionRequiredMixin) ---

    def test_guardian_cbv_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse("service_list"), HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp["Location"])

    def test_guardian_cbv_authed_unauthorised_403(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("service_list"), HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 403)
