from urllib.parse import parse_qs, urlsplit

from constance.test import override_config
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["localhost"])
class AdfsAutoLoginNextTests(TestCase):
    @override_config(ADFS_ENABLED=True, ADFS_AUTO_LOGIN=True)
    def test_multi_param_next_survives_the_bounce(self):
        nxt = "/o/authorize/?client_id=abc&response_type=code&state=xyz"
        resp = self.client.get(reverse("login"), {"next": nxt}, HTTP_HOST="localhost")
        self.assertEqual(resp.status_code, 302)
        location = urlsplit(resp["Location"])
        self.assertEqual(location.path, reverse("django_auth_adfs:login"))
        self.assertEqual(parse_qs(location.query)["next"], [nxt])
