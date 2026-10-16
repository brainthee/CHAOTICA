import itertools

from django.core.cache import cache
from django.utils import timezone
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from chaotica_utils.models import User
from jobtracker.models import (
    Client,
    Job,
    OrganisationalUnit,
    OrganisationalUnitMember,
    OrganisationalUnitRole,
    Phase,
)


_seq = itertools.count(1)


def _reset_cache():
    """Forget throttle counters and the setup-needed flag. Never
    ``cache.clear()``: on Redis that flushes the db every session shares."""
    cache.delete_pattern("throttle_*")
    cache.delete("chaotica_setup_needed")


def make_member(user, unit, roles=("Consultant",)):
    """Make ``user`` a current member of ``unit`` with the named roles and sync
    their guardian perms. Returns a fresh ``User`` (guardian caches perms on
    the instance)."""
    membership = OrganisationalUnitMember.objects.create(unit=unit, member=user)
    for name in roles:
        role, _ = OrganisationalUnitRole.objects.get_or_create(name=name)
        membership.roles.add(role)
    unit.sync_permissions(users=[user])
    return User.objects.get(pk=user.pk)


def leave_unit(user, unit):
    OrganisationalUnitMember.objects.filter(unit=unit, member=user).update(
        left_date=timezone.now()
    )
    unit.sync_permissions(users=[user])


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
        _reset_cache()
        self.addCleanup(_reset_cache)
        self.client = APIClient(HTTP_HOST="testserver")

    def make_job(self, unit=None, client=None, **kwargs):
        n = next(_seq)
        unit = unit or OrganisationalUnit.objects.create(name=f"Unit {n}")
        client = client or Client.objects.create(name=f"Client {n}")
        kwargs.setdefault("title", "Job")
        kwargs.setdefault("created_by", self.superuser)
        kwargs.setdefault("account_manager", self.superuser)
        return Job.objects.create(unit=unit, client=client, **kwargs)

    def make_phase(self, job, **kwargs):
        kwargs.setdefault("title", "Phase")
        return Phase.objects.create(job=job, **kwargs)

    def as_user(self, user):
        client = APIClient(HTTP_HOST="testserver")
        client.force_authenticate(user)
        return client

    def assert_same_ids(self, resp, queryset):
        """Parity: an API list returns exactly ``queryset``'s rows."""
        self.assertEqual(resp.status_code, 200, resp.content)
        got = {row["id"] for row in resp.json()["results"]}
        self.assertEqual(got, set(queryset.values_list("pk", flat=True)))

    def token_client(self, user, **extra):
        token, _ = Token.objects.get_or_create(user=user)
        client = APIClient(HTTP_HOST="testserver", **extra)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client
