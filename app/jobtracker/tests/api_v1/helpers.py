from django.core.cache import cache
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from chaotica_utils.models import User


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiV1TestCase(APITestCase):
    """Base for /api/v1/ tests.

    The first user created is promoted to superuser by ``User.save()``, so a
    sacrificial superuser is always created first; ``normal`` is a plain user.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin"
        )
        cls.normal = User.objects.create_user(
            email="normal@example.com", password="pw-normal"
        )

    def setUp(self):
        super().setUp()
        cache.clear()  # throttle counters, setup-needed flag
        self.addCleanup(cache.clear)
        self.client = APIClient(HTTP_HOST="testserver")

    def token_client(self, user, **extra):
        token, _ = Token.objects.get_or_create(user=user)
        client = APIClient(HTTP_HOST="testserver", **extra)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client
