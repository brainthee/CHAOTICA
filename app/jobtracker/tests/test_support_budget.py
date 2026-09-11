"""Tests for the support-team budget allocation engine, the per-job override /
template mechanism and the per-period draw-down ledger.

The engine is a read-only computed view (sibling to the billing-allocation
tests). The headline oracle is the Accenture MMP spreadsheet: 6 members at 100%
+ 2 at 20% give a percent sum of 640, so a 100% member's share is
100/640 = 0.15625.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase, Client as TestHttpClient
from django.urls import reverse
from guardian.shortcuts import assign_perm

from chaotica_utils.models import User, UserCost
from chaotica_utils.utils import (
    build_job_support_budget,
    build_user_support_budget,
    resolve_lcr,
)
from jobtracker.models import (
    Client,
    Job,
    OrganisationalUnit,
    OrganisationalUnitSupportTemplateMember,
    JobSupportTeamRole,
    SupportBudgetDraw,
)


class SupportBudgetTestBase(TestCase):
    def setUp(self):
        self.root = User.objects.create_user(email="root@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="UKI")
        self.client_obj = Client.objects.create(name="Acme")  # hours_in_day default 7.5
        self.job = Job.objects.create(
            title="Test job",
            client=self.client_obj,
            unit=self.unit,
            created_by=self.root,
            account_manager=self.root,
            revenue=Decimal("10000"),
        )

    def _user(self, n, lcr=None):
        u = User.objects.create_user(email="u%d@test.com" % n, password="pw")
        if lcr is not None:
            UserCost.objects.create(
                user=u, effective_from=date(2020, 1, 1), cost_per_hour=Decimal(str(lcr))
            )
        return u

    def _role(self, user, percent):
        return JobSupportTeamRole.objects.create(
            job=self.job, user=user, profile_percent=Decimal(str(percent))
        )


class JobSupportRoleEnumTests(TestCase):
    def test_role_values_are_distinct(self):
        # Regression: COMMERCIAL and QA both used to be 1, so selecting
        # "Commercial" stored a value that rendered as "QA".
        from jobtracker.enums import JobSupportRole

        values = [v for v, _ in JobSupportRole.CHOICES]
        self.assertEqual(len(values), len(set(values)), "role choice values collide")
        self.assertNotEqual(JobSupportRole.COMMERCIAL, JobSupportRole.QA)

    def test_commercial_and_qa_display_correctly(self):
        from jobtracker.enums import JobSupportRole

        root = User.objects.create_user(email="root-enum@test.com", password="pw")
        unit = OrganisationalUnit.objects.create(name="U-enum")
        client = Client.objects.create(name="C-enum")
        job = Job.objects.create(
            title="J", client=client, unit=unit, created_by=root, account_manager=root
        )
        u1 = User.objects.create_user(email="comm-enum@test.com", password="pw")
        u2 = User.objects.create_user(email="qa-enum@test.com", password="pw")
        comm = JobSupportTeamRole.objects.create(
            job=job, user=u1, role=JobSupportRole.COMMERCIAL
        )
        qa = JobSupportTeamRole.objects.create(
            job=job, user=u2, role=JobSupportRole.QA
        )
        self.assertEqual(comm.get_role_display(), "Commercial")
        self.assertEqual(qa.get_role_display(), "QA")


class EngineOracleTests(SupportBudgetTestBase):
    def test_spreadsheet_oracle(self):
        # 6 @ 100% + 2 @ 20% => percent_sum 640; a 100% member's share = 0.15625.
        full = [self._user(i, lcr=50) for i in range(6)]
        partial = [self._user(100 + i, lcr=50) for i in range(2)]
        for u in full:
            self._role(u, 100)
        for u in partial:
            self._role(u, 20)

        b = build_job_support_budget(self.job, on_date=date(2026, 9, 9))

        self.assertEqual(b["premium"], Decimal("8"))
        self.assertEqual(b["pool"], Decimal("800.00"))  # 10000 * 8%
        self.assertEqual(b["percent_sum"], Decimal("640.00"))

        m0 = b["per_member"][full[0].id]
        self.assertEqual(m0["share"], Decimal("0.15625"))
        self.assertEqual(m0["share_percent"], Decimal("15.625"))
        self.assertEqual(m0["budget_money"], Decimal("125.00000"))
        # 125 / 50 = 2.5h; 2.5 / 7.5 = 0.3333..d
        self.assertEqual(m0["budget_hours"], Decimal("2.5"))
        self.assertEqual(m0["budget_days"].quantize(Decimal("0.0001")), Decimal("0.3333"))

        mp = b["per_member"][partial[0].id]
        self.assertEqual(mp["share"], Decimal("0.03125"))  # 20 / 640
        self.assertEqual(mp["budget_money"], Decimal("25.00000"))

        # Shares sum to 1 (allowing for repeating decimals).
        total_share = sum(m["share"] for m in b["per_member"].values())
        self.assertEqual(total_share.quantize(Decimal("0.0001")), Decimal("1.0000"))

    def test_zero_revenue_warns_and_zeroes(self):
        self.job.revenue = Decimal("0")
        self.job.save()
        u = self._user(1, lcr=50)
        self._role(u, 100)
        b = build_job_support_budget(self.job)
        self.assertEqual(b["pool"], Decimal("0.00"))
        self.assertEqual(b["per_member"][u.id]["budget_money"], Decimal("0.00"))
        self.assertTrue(any("no revenue" in w for w in b["warnings"]))

    def test_missing_lcr_gives_none_hours_with_warning(self):
        u = self._user(1)  # no UserCost
        self._role(u, 100)
        b = build_job_support_budget(self.job)
        m = b["per_member"][u.id]
        self.assertIsNotNone(m["budget_money"])  # money still computed
        self.assertIsNone(m["budget_hours"])
        self.assertIsNone(m["remaining_hours"])
        self.assertTrue(any("loaded cost rate" in w for w in b["warnings"]))

    def test_zero_percent_sum_guarded(self):
        u = self._user(1, lcr=50)
        self._role(u, 0)
        b = build_job_support_budget(self.job)
        self.assertEqual(b["per_member"][u.id]["share"], Decimal("0"))
        self.assertTrue(any("sum to zero" in w for w in b["warnings"]))


class PremiumResolutionTests(SupportBudgetTestBase):
    def test_precedence_override_unit_constance(self):
        # Constance default (no unit/job value) -> unit default -> job override.
        self.unit.support_premium_default = Decimal("12")
        self.unit.save()
        self.assertEqual(self.job.get_effective_premium(), Decimal("12"))

        self.job.support_premium_override = Decimal("15")
        self.assertEqual(self.job.get_effective_premium(), Decimal("15"))


class LCRDateAwarenessTests(SupportBudgetTestBase):
    def test_cost_on_picks_latest_eligible(self):
        u = self._user(1)
        UserCost.objects.create(
            user=u, effective_from=date(2024, 1, 1), cost_per_hour=Decimal("40")
        )
        UserCost.objects.create(
            user=u, effective_from=date(2026, 1, 1), cost_per_hour=Decimal("60")
        )
        self.assertEqual(resolve_lcr(u, date(2025, 6, 1)), Decimal("40"))
        self.assertEqual(resolve_lcr(u, date(2026, 6, 1)), Decimal("60"))
        # Before any effective date -> falls back to None (no undated row).
        self.assertIsNone(resolve_lcr(u, date(2020, 1, 1)))


class LedgerTests(SupportBudgetTestBase):
    def _remaining(self, user, on):
        # What production reads: the engine's per-member remaining hours.
        budget = self.job.get_support_budget(on_date=on)
        return budget["per_member"][user.id]["remaining_hours"]

    def test_draws_reduce_remaining_and_carry_forward(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)  # budget_money 800 -> 16h @50
        on = date(2026, 9, 30)
        self.assertEqual(self._remaining(u, on), Decimal("16"))

        SupportBudgetDraw.objects.create(
            support_role=role,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 7),
            hours_drawn=Decimal("5"),
            created_by=self.root,
        )
        SupportBudgetDraw.objects.create(
            support_role=role,
            period_start=date(2026, 9, 8),
            period_end=date(2026, 9, 14),
            hours_drawn=Decimal("4"),
            created_by=self.root,
        )
        self.assertEqual(role.drawn_hours(), Decimal("9"))
        self.assertEqual(self._remaining(u, on), Decimal("7"))

    def test_over_draw_goes_negative(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        SupportBudgetDraw.objects.create(
            support_role=role,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 7),
            hours_drawn=Decimal("20"),
            created_by=self.root,
        )
        self.assertEqual(self._remaining(u, date(2026, 9, 30)), Decimal("-4"))

    def test_draw_denormalises_user(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        d = SupportBudgetDraw.objects.create(
            support_role=role,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 7),
            hours_drawn=Decimal("1"),
            created_by=self.root,
        )
        self.assertEqual(d.user_id, u.id)

    def test_user_rollup_period_filter(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        SupportBudgetDraw.objects.create(
            support_role=role,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 7),
            hours_drawn=Decimal("3"),
            created_by=self.root,
        )
        roll = build_user_support_budget(
            u, start=date(2026, 9, 1), end=date(2026, 9, 30)
        )
        self.assertEqual(len(roll["per_job"]), 1)
        entry = roll["per_job"][0]
        self.assertEqual(entry["period_drawn_hours"], Decimal("3"))
        self.assertEqual(entry["remaining_hours"], Decimal("13"))  # 16 - 3


class TemplateApplyTests(SupportBudgetTestBase):
    def _template(self, user, percent):
        return OrganisationalUnitSupportTemplateMember.objects.create(
            unit=self.unit, user=user, profile_percent=Decimal(str(percent))
        )

    def test_apply_creates_rows(self):
        u1 = self._user(1, lcr=50)
        u2 = self._user(2, lcr=50)
        self._template(u1, 100)
        self._template(u2, 20)
        summary = self.unit.apply_support_template_to_job(self.job)
        self.assertEqual(summary["created"], 2)
        self.assertEqual(self.job.supporting_team.count(), 2)
        self.assertEqual(
            JobSupportTeamRole.objects.get(job=self.job, user=u2).profile_percent,
            Decimal("20.00"),
        )

    def test_override_survives_reapply(self):
        u1 = self._user(1, lcr=50)
        self._template(u1, 100)
        self.unit.apply_support_template_to_job(self.job)
        row = JobSupportTeamRole.objects.get(job=self.job, user=u1)
        row.profile_percent = Decimal("50")
        row.is_overridden = True
        row.save()

        # Change template, re-apply: overridden row is left alone.
        tmpl = OrganisationalUnitSupportTemplateMember.objects.get(unit=self.unit, user=u1)
        tmpl.profile_percent = Decimal("100")
        tmpl.save()
        summary = self.unit.apply_support_template_to_job(self.job)
        self.assertEqual(summary["skipped"], 1)
        row.refresh_from_db()
        self.assertEqual(row.profile_percent, Decimal("50.00"))

        # Force overwrite resets it.
        summary = self.unit.apply_support_template_to_job(self.job, overwrite=True)
        self.assertEqual(summary["updated"], 1)
        row.refresh_from_db()
        self.assertEqual(row.profile_percent, Decimal("100.00"))
        self.assertFalse(row.is_overridden)

    def test_auto_applied_on_job_create(self):
        u1 = self._user(1, lcr=50)
        self._template(u1, 100)
        new_job = Job.objects.create(
            title="Auto",
            client=self.client_obj,
            unit=self.unit,
            created_by=self.root,
            account_manager=self.root,
            revenue=Decimal("5000"),
        )
        self.assertTrue(
            JobSupportTeamRole.objects.filter(job=new_job, user=u1).exists()
        )


class SupportBudgetViewTests(SupportBudgetTestBase):
    """The per-user page surfaces the support budget; money/LCR are gated on the
    ``can_view_loaded_costs`` permission (self + manager access unchanged)."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(email="owner@test.com", password="pw")
        self.manager = User.objects.create_user(email="mgr@test.com", password="pw")
        self.owner.manager = self.manager
        self.owner.save()
        self.stranger = User.objects.create_user(email="str@test.com", password="pw")
        UserCost.objects.create(
            user=self.owner, effective_from=date(2020, 1, 1), cost_per_hour=Decimal("50")
        )
        # 10000 * 8% = 800 pool, single member -> £800.00 budget, 16h.
        self.role = JobSupportTeamRole.objects.create(
            job=self.job, user=self.owner, profile_percent=Decimal("100")
        )
        self.http = TestHttpClient(HTTP_HOST="localhost")

    def _draw_url(self):
        return reverse(
            "user_support_draw",
            kwargs={"email": self.owner.email, "role_pk": self.role.pk},
        )

    def _url(self):
        return reverse("user_code_allocation", kwargs={"email": self.owner.email})

    def test_self_sees_hours_but_not_money(self):
        self.http.force_login(self.owner)
        resp = self.http.get(self._url())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Support budget", body)
        self.assertIn("16.0", body)  # budget hours visible
        self.assertNotIn("800.00", body)  # money hidden without finance perm

    def test_finance_permitted_sees_money(self):
        assign_perm("jobtracker.can_view_loaded_costs", self.manager, self.unit)
        self.http.force_login(self.manager)
        resp = self.http.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("800.00", resp.content.decode())

    def test_money_gated_per_unit(self):
        # Owner also has a support role in another unit the manager can't see
        # finances for; the manager must NOT see that unit's budget money.
        other_unit = OrganisationalUnit.objects.create(name="Other-money")
        other_job = Job.objects.create(
            title="Other job", client=self.client_obj, unit=other_unit,
            created_by=self.root, account_manager=self.root, revenue=Decimal("20000"),
        )
        JobSupportTeamRole.objects.create(
            job=other_job, user=self.owner, profile_percent=Decimal("100")
        )
        # Manager has finance on the first unit only.
        assign_perm("jobtracker.can_view_loaded_costs", self.manager, self.unit)
        self.http.force_login(self.manager)
        body = self.http.get(self._url()).content.decode()
        self.assertIn("800.00", body)       # unit they can see
        self.assertNotIn("1600.00", body)   # other unit's money must be hidden

    def test_stranger_forbidden(self):
        self.http.force_login(self.stranger)
        resp = self.http.get(self._url())
        self.assertEqual(resp.status_code, 403)

    def test_job_detail_renders_support_widget(self):
        # Superuser bypasses guardian; catches template errors in the widget.
        su = User.objects.create_superuser(email="su@test.com", password="pw")
        self.http.force_login(su)
        resp = self.http.get(reverse("job_detail", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Support", resp.content.decode())

    def test_sales_dashboard_partial_renders(self):
        su = User.objects.create_superuser(email="su-sales@test.com", password="pw")
        self.http.force_login(su)
        resp = self.http.get(reverse("view_job_sales", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Revenue", body)
        self.assertIn("Margin vs target", body)

    def test_sales_dashboard_requires_job_view_perm(self):
        self.http.force_login(self.stranger)
        resp = self.http.get(reverse("view_job_sales", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 403)

    def test_auto_cash_out_fills_period(self):
        from jobtracker.models import SupportBudgetDraw

        self.http.force_login(self.owner)
        url = reverse("user_support_auto_draw", kwargs={"email": self.owner.email})
        resp = self.http.post(url, {"start": "2026-09-01", "end": "2026-09-14"})
        self.assertEqual(resp.status_code, 302)
        draws = SupportBudgetDraw.objects.filter(
            support_role__user=self.owner, period_start=date(2026, 9, 1)
        )
        self.assertEqual(draws.count(), 1)
        self.assertEqual(draws.first().hours_drawn, Decimal("16.00"))  # 800/50
        # Idempotent: clicking again doesn't duplicate.
        self.http.post(url, {"start": "2026-09-01", "end": "2026-09-14"})
        self.assertEqual(draws.count(), 1)

    def test_auto_cash_out_forbidden_for_stranger(self):
        self.http.force_login(self.stranger)
        resp = self.http.post(
            reverse("user_support_auto_draw", kwargs={"email": self.owner.email}),
            {"start": "2026-09-01", "end": "2026-09-14"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_cash_out_button_on_page(self):
        self.http.force_login(self.owner)
        resp = self.http.get(self._url())
        self.assertIn("Cash out", resp.content.decode())

    def test_self_can_cash_out(self):
        from jobtracker.models import SupportBudgetDraw

        self.http.force_login(self.owner)
        # GET returns the modal with the current period pre-filled.
        resp = self.http.get(self._draw_url())
        self.assertEqual(resp.status_code, 200)
        # POST records the draw against the owner's own role.
        resp = self.http.post(
            self._draw_url(),
            {
                "period_start": "2026-09-01",
                "period_end": "2026-09-14",
                "hours_drawn": "3",
            },
        )
        self.assertTrue(resp.json()["form_is_valid"])
        draw = SupportBudgetDraw.objects.get(support_role=self.role)
        self.assertEqual(draw.hours_drawn, Decimal("3"))
        self.assertEqual(draw.user_id, self.owner.id)
        self.assertEqual(draw.created_by_id, self.owner.id)

    def test_manager_can_cash_out_for_report(self):
        self.http.force_login(self.manager)
        resp = self.http.post(
            self._draw_url(),
            {"period_start": "2026-09-01", "period_end": "2026-09-14", "hours_drawn": "2"},
        )
        self.assertTrue(resp.json()["form_is_valid"])

    def test_stranger_cannot_cash_out(self):
        self.http.force_login(self.stranger)
        resp = self.http.post(
            self._draw_url(),
            {"period_start": "2026-09-01", "period_end": "2026-09-14", "hours_drawn": "2"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_role_must_belong_to_profile_owner(self):
        # A role on a different user can't be drawn via this profile's URL.
        other = User.objects.create_user(email="other@test.com", password="pw")
        other_role = JobSupportTeamRole.objects.create(
            job=self.job, user=other, profile_percent=Decimal("100")
        )
        self.http.force_login(self.owner)
        url = reverse(
            "user_support_draw",
            kwargs={"email": self.owner.email, "role_pk": other_role.pk},
        )
        resp = self.http.post(
            url, {"period_start": "2026-09-01", "period_end": "2026-09-14", "hours_drawn": "1"}
        )
        self.assertEqual(resp.status_code, 404)


class FinanceTabViewTests(SupportBudgetTestBase):
    """The org-unit Finance tab (template + LCR + settings) lives in the main UI
    and is gated on ``can_view_loaded_costs`` — no admin needed."""

    def setUp(self):
        super().setUp()
        self.finance = User.objects.create_user(email="fin@test.com", password="pw")
        self.plain = User.objects.create_user(email="plain@test.com", password="pw")
        assign_perm("jobtracker.view_organisationalunit", self.finance, self.unit)
        assign_perm("jobtracker.can_view_loaded_costs", self.finance, self.unit)
        assign_perm("jobtracker.view_organisationalunit", self.plain, self.unit)
        self.member_user = User.objects.create_user(email="m@test.com", password="pw")
        self.membership = self.unit.members.create(member=self.member_user)
        self.http = TestHttpClient(HTTP_HOST="localhost")

    def _detail_url(self):
        return reverse("organisationalunit_detail", kwargs={"slug": self.unit.slug})

    def test_finance_tab_visible_with_perm(self):
        self.http.force_login(self.finance)
        resp = self.http.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Finance", body)
        self.assertIn("Loaded Cost Rates", body)

    def test_finance_tab_hidden_without_perm(self):
        self.http.force_login(self.plain)
        resp = self.http.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Loaded Cost Rates", resp.content.decode())

    def test_crud_endpoints_forbidden_without_perm(self):
        self.http.force_login(self.plain)
        for name, kwargs in [
            ("organisationalunit_finance_settings", {"slug": self.unit.slug}),
            ("organisationalunit_support_template_add", {"slug": self.unit.slug}),
            ("organisationalunit_set_lcr", {"slug": self.unit.slug, "member_pk": self.membership.pk}),
        ]:
            resp = self.http.get(reverse(name, kwargs=kwargs))
            self.assertEqual(resp.status_code, 403, name)

    def test_add_template_member_and_set_lcr(self):
        self.http.force_login(self.finance)
        # Add a template member.
        resp = self.http.post(
            reverse("organisationalunit_support_template_add", kwargs={"slug": self.unit.slug}),
            {"user": self.member_user.pk, "role": 0, "profile_percent": "100"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertTrue(
            OrganisationalUnitSupportTemplateMember.objects.filter(
                unit=self.unit, user=self.member_user
            ).exists()
        )
        # Set a loaded cost rate for a member.
        resp = self.http.post(
            reverse("organisationalunit_set_lcr", kwargs={"slug": self.unit.slug, "member_pk": self.membership.pk}),
            {"effective_from": "2026-01-01", "cost_per_hour": "55.00"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertEqual(
            UserCost.objects.get(user=self.member_user).cost_per_hour, Decimal("55.00")
        )

    def test_edit_and_delete_template_member(self):
        self.http.force_login(self.finance)
        tm = OrganisationalUnitSupportTemplateMember.objects.create(
            unit=self.unit, user=self.member_user, profile_percent=Decimal("100")
        )
        # GET the edit modal (this is the path that hit the NameError).
        resp = self.http.get(
            reverse("organisationalunit_support_template_edit", kwargs={"slug": self.unit.slug, "pk": tm.pk})
        )
        self.assertEqual(resp.status_code, 200)
        # POST an edit.
        resp = self.http.post(
            reverse("organisationalunit_support_template_edit", kwargs={"slug": self.unit.slug, "pk": tm.pk}),
            {"user": self.member_user.pk, "role": 0, "profile_percent": "20"},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        tm.refresh_from_db()
        self.assertEqual(tm.profile_percent, Decimal("20.00"))
        # Delete it.
        resp = self.http.post(
            reverse("organisationalunit_support_template_delete", kwargs={"slug": self.unit.slug, "pk": tm.pk}),
            {"user_action": "approve_action"},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertFalse(
            OrganisationalUnitSupportTemplateMember.objects.filter(pk=tm.pk).exists()
        )

    def test_edit_premium_default(self):
        self.http.force_login(self.finance)
        resp = self.http.post(
            reverse("organisationalunit_finance_settings", kwargs={"slug": self.unit.slug}),
            {"support_premium_default": "12.50"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["form_is_valid"])
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.support_premium_default, Decimal("12.50"))
