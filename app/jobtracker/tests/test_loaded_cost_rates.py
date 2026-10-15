"""Operations → Loaded Cost Rates: site-wide LCR list + set-rate modal.

Visibility follows ``can_view_loaded_costs`` per unit; setting a rate follows
``can_manage_user_lcr`` (the permission on every unit the person is in).
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase, Client as TestHttpClient
from django.urls import reverse
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User, UserCost
from jobtracker.models import OrganisationalUnit


class LoadedCostRatesTests(TestCase):
    def setUp(self):
        # The first user is auto-promoted to superuser; keep it out of the way.
        self.root = User.objects.create_user(email="root@test.com", password="pw")
        self.uki = OrganisationalUnit.objects.create(name="UKI")
        self.prague = OrganisationalUnit.objects.create(name="Prague")
        self.finance = User.objects.create_user(
            email="fin@test.com", password="pw", first_name="Fin", last_name="Ance"
        )
        self.finance.is_superuser = False
        self.finance.save()
        assign_perm("jobtracker.can_view_loaded_costs", self.finance, self.uki)

        self.ada = User.objects.create_user(
            email="ada@test.com", password="pw", first_name="Ada", last_name="Lovelace"
        )
        self.uki.members.create(member=self.ada)
        UserCost.objects.create(
            user=self.ada, effective_from=date(2026, 1, 1), cost_per_hour=Decimal("50")
        )
        # In both units: visible to UKI finance, but read only.
        self.bob = User.objects.create_user(
            email="bob@test.com", password="pw", first_name="Bob", last_name="Babbage"
        )
        self.uki.members.create(member=self.bob)
        self.prague.members.create(member=self.bob)
        # Prague only: never visible to UKI finance.
        self.cat = User.objects.create_user(
            email="cat@test.com", password="pw", first_name="Cat", last_name="Hopper"
        )
        self.prague.members.create(member=self.cat)

        self.plain = User.objects.create_user(email="plain@test.com", password="pw")
        self.http = TestHttpClient(HTTP_HOST="localhost")

    def _list(self, **params):
        return self.http.get(reverse("lcr_list"), params)

    def test_forbidden_without_perm(self):
        self.http.force_login(self.plain)
        self.assertEqual(self._list().status_code, 403)
        url = reverse("lcr_set", kwargs={"user_pk": self.ada.pk})
        self.assertEqual(self.http.get(url).status_code, 403)

    def test_menu_entry_follows_perm(self):
        self.http.force_login(self.finance)
        dash = self.http.get(reverse("dashboard"))
        self.assertContains(dash, reverse("lcr_list"))
        self.http.force_login(self.plain)
        dash = self.http.get(reverse("dashboard"))
        self.assertNotContains(dash, reverse("lcr_list"))

    def test_lists_only_people_in_my_units(self):
        self.http.force_login(self.finance)
        resp = self._list()
        self.assertEqual(resp.status_code, 200)
        emails = [r["user"].email for r in resp.context["rows"]]
        self.assertEqual(sorted(emails), ["ada@test.com", "bob@test.com"])
        # Only my units are offered as filters.
        self.assertEqual([u.name for u in resp.context["units"]], ["UKI"])

    def test_can_set_needs_perm_on_every_unit(self):
        self.http.force_login(self.finance)
        rows = {r["user"].email: r for r in self._list().context["rows"]}
        self.assertTrue(rows["ada@test.com"]["can_set"])
        self.assertFalse(rows["bob@test.com"]["can_set"])
        bob_url = reverse("lcr_set", kwargs={"user_pk": self.bob.pk})
        resp = self.http.post(
            bob_url, {"effective_from": "2026-02-01", "cost_per_hour": "40"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(UserCost.objects.filter(user=self.bob).exists())
        # Out-of-remit person: no access at all.
        cat_url = reverse("lcr_set", kwargs={"user_pk": self.cat.pk})
        self.assertEqual(self.http.get(cat_url).status_code, 403)

    def test_cannot_set_own_rate(self):
        self.uki.members.create(member=self.finance)
        # Joining re-syncs unit perms from roles; re-grant the direct one.
        assign_perm("jobtracker.can_view_loaded_costs", self.finance, self.uki)
        self.http.force_login(self.finance)
        rows = {r["user"].email: r for r in self._list().context["rows"]}
        self.assertFalse(rows["fin@test.com"]["can_set"])
        url = reverse("lcr_set", kwargs={"user_pk": self.finance.pk})
        self.assertEqual(self.http.get(url).status_code, 403)

    def test_unit_filter_outside_remit_is_forbidden(self):
        self.http.force_login(self.finance)
        self.assertEqual(self._list(unit=self.prague.slug).status_code, 403)
        self.assertEqual(self._list(unit=self.uki.slug).status_code, 200)

    def test_rate_and_search_filters(self):
        self.http.force_login(self.finance)
        missing = [r["user"].email for r in self._list(rate="missing").context["rows"]]
        self.assertEqual(missing, ["bob@test.com"])
        has = [r["user"].email for r in self._list(rate="set").context["rows"]]
        self.assertEqual(has, ["ada@test.com"])
        found = [r["user"].email for r in self._list(q="lovel").context["rows"]]
        self.assertEqual(found, ["ada@test.com"])

    def test_superuser_sees_everyone_and_can_set(self):
        self.http.force_login(self.root)
        rows = {r["user"].email: r for r in self._list().context["rows"]}
        self.assertIn("cat@test.com", rows)
        self.assertTrue(all(r["can_set"] for r in rows.values()))

    def test_set_rate_adds_a_dated_row(self):
        self.http.force_login(self.finance)
        url = reverse("lcr_set", kwargs={"user_pk": self.ada.pk})
        resp = self.http.post(
            url, {"effective_from": "2026-06-01", "cost_per_hour": "55.00"}
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertEqual(
            list(
                UserCost.objects.filter(user=self.ada)
                .order_by("effective_from")
                .values_list("cost_per_hour", flat=True)
            ),
            [Decimal("50.00"), Decimal("55.00")],
        )

    def test_set_rate_rejects_duplicate_date_and_bad_rate(self):
        self.http.force_login(self.finance)
        url = reverse("lcr_set", kwargs={"user_pk": self.ada.pk})
        resp = self.http.post(
            url, {"effective_from": "2026-01-01", "cost_per_hour": "60"}
        )
        self.assertFalse(resp.json()["form_is_valid"])
        self.assertIn("effective_from", resp.json()["form_errors"])
        for bad in ("0", "-5", ""):
            resp = self.http.post(
                url, {"effective_from": "2026-03-01", "cost_per_hour": bad}
            )
            self.assertFalse(resp.json()["form_is_valid"], bad)
        self.assertEqual(UserCost.objects.filter(user=self.ada).count(), 1)
