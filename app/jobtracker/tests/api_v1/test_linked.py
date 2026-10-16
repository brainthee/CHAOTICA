"""Linked entities (A6): clients, contacts, frameworks, users, org units."""

from datetime import date

from django.conf import settings
from django.urls import reverse

from chaotica_utils.models import Group, User
from jobtracker.models import (
    Client,
    Contact,
    FrameworkAgreement,
    Skill,
    SkillCategory,
    UserSkill,
)

from .helpers import ApiV1TestCase, make_member


class ContactFrameworkBindingTests(ApiV1TestCase):
    """Security: a contact/framework pk resolved under any client's slug."""

    def setUp(self):
        super().setUp()
        self.mine = Client.objects.create(name="Mine")
        self.theirs = Client.objects.create(name="Theirs")
        self.contact = Contact.objects.create(company=self.theirs, first_name="Eve")
        self.framework = FrameworkAgreement.objects.create(
            client=self.theirs, name="FW", start_date=date(2026, 1, 1), total_days=10
        )
        self.client.force_login(self.superuser)

    def _status(self, name, client, pk):
        return self.client.get(
            reverse(name, kwargs={"client_slug": client.slug, "pk": pk})
        ).status_code

    def test_contact_bound_to_client(self):
        for name in (
            "client_contact_detail",
            "client_contact_update",
            "client_contact_delete",
        ):
            self.assertEqual(self._status(name, self.mine, self.contact.pk), 404, name)
        # (The contact detail page itself has no template; edit is the page.)
        self.assertEqual(
            self._status("client_contact_update", self.theirs, self.contact.pk), 200
        )

    def test_framework_bound_to_client(self):
        for name in (
            "client_framework_detail",
            "client_framework_update",
            "client_framework_delete",
        ):
            self.assertEqual(
                self._status(name, self.mine, self.framework.pk), 404, name
            )
        self.assertEqual(
            self._status("client_framework_detail", self.theirs, self.framework.pk), 200
        )


class ClientApiTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.job = self.make_job()
        self.acme = self.job.client
        self.contact = Contact.objects.create(company=self.acme, first_name="Ada")
        self.framework = FrameworkAgreement.objects.create(
            client=self.acme, name="MSA", start_date=date(2026, 1, 1), total_days=20
        )
        self.su = self.as_user(self.superuser)

    def test_detail_and_sub_lists(self):
        body = self.su.get(f"/api/v1/clients/{self.acme.pk}/").json()
        self.assertEqual([c["id"] for c in body["contacts"]], [self.contact.pk])
        self.assertEqual(
            body["contacts"][0]["url"], f"/api/v1/contacts/{self.contact.pk}/"
        )
        self.assertEqual([f["id"] for f in body["frameworks"]], [self.framework.pk])
        jobs = self.su.get(f"/api/v1/clients/{self.acme.pk}/jobs/").json()
        self.assertEqual([j["id"] for j in jobs["results"]], [self.job.pk])
        contacts = self.su.get(f"/api/v1/clients/{self.acme.pk}/contacts/").json()
        self.assertEqual(contacts["results"][0]["client"]["id"], self.acme.pk)

    def test_contact_needs_permission(self):
        resp = self.as_user(self.normal).get(f"/api/v1/contacts/{self.contact.pk}/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(
            self.su.get(f"/api/v1/contacts/{self.contact.pk}/").json()["first_name"],
            "Ada",
        )

    def test_framework_usage(self):
        body = self.su.get(f"/api/v1/frameworks/{self.framework.pk}/").json()
        self.assertEqual(body["usage"]["days_available"], 20.0)
        self.assertEqual(body["usage"]["jobs"], [])


class UserApiTests(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.boss = User.objects.create_user(email="boss@example.com", password="pw")
        self.normal.manager = self.boss
        self.normal.save()
        cat = SkillCategory.objects.create(name="Web")
        UserSkill.objects.create(
            user=self.normal,
            skill=Skill.objects.create(name="XSS", category=cat),
            rating=2,
        )
        self.role_holder = User.objects.create_user(
            email="colleague@example.com", password="pw"
        )
        group, _ = Group.objects.get_or_create(
            name=settings.GLOBAL_GROUP_PREFIX + "User"
        )
        self.role_holder.groups.add(group)

    def test_contact_block(self):
        mine = self.as_user(self.normal).get(f"/api/v1/users/{self.normal.pk}/").json()
        self.assertEqual(mine["contact"]["email"], "normal@example.com")
        self.assertEqual(mine["manager"]["id"], self.boss.pk)
        # Managers see their reports via the list scope, but contact details
        # need view_user.
        theirs = self.as_user(self.boss).get(f"/api/v1/users/{self.normal.pk}/").json()
        self.assertIsNone(theirs["contact"])
        su = self.as_user(self.superuser).get(f"/api/v1/users/{self.normal.pk}/").json()
        self.assertIsNotNone(su["contact"])

    def test_profile_gate_and_competency(self):
        url = f"/api/v1/users/{self.normal.pk}/profile/"
        loner = User.objects.create_user(email="loner@example.com", password="pw")
        self.assertEqual(self.as_user(loner).get(url).status_code, 403)
        colleague = self.as_user(self.role_holder).get(url).json()
        self.assertIsNone(colleague["skills"])
        self.assertIsNone(colleague["contact"])
        boss = User.objects.get(pk=self.boss.pk)
        boss.groups.add(Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX + "User"))
        body = self.as_user(boss).get(url).json()
        self.assertEqual([s["skill"]["display"] for s in body["skills"]], ["XSS"])

    def test_profile_page_tolerates_bad_dates(self):
        self.client.force_login(self.superuser)
        url = reverse("user_profile", kwargs={"email": self.normal.email})
        for params in (
            {"dateRange": "nope to never"},
            {"start_date": "x", "end_date": "y"},
        ):
            self.assertEqual(self.client.get(url, params).status_code, 200, params)


class OrgUnitApiTests(ApiV1TestCase):
    def test_detail(self):
        job = self.make_job()
        member = make_member(
            User.objects.create_user(email="m@example.com", password="pw"), job.unit
        )
        body = (
            self.as_user(self.superuser).get(f"/api/v1/org-units/{job.unit.pk}/").json()
        )
        row = next(r for r in body["members"] if r["user"]["id"] == member.pk)
        self.assertEqual(row["roles"], ["Consultant"])
        self.assertTrue(row["is_consultant"])
        self.assertIsInstance(body["utilisation_4wk"], float)

    def test_header_tile_still_works(self):
        job = self.make_job()
        self.client.force_login(self.superuser)
        resp = self.client.get(
            reverse("orgunit_header_stats_partial", kwargs={"slug": job.unit.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("utilisation_4wk", resp.json())
