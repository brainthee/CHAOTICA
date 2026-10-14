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

from chaotica_utils.models import User, UserCost, get_sentinel_user
from django.core.exceptions import ValidationError

from chaotica_utils.utils import (
    auto_cash_out,
    build_job_support_budget,
    build_user_support_budget,
    create_support_draw,
    resolve_lcr,
)
from jobtracker.enums import JobStatuses
from jobtracker.models import (
    Client,
    Job,
    OrganisationalUnit,
    OrganisationalUnitSupportTemplateMember,
    JobSupportTeamRole,
    SupportBudgetDraw,
    SupportProfile,
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
    """Cash-outs go through ``create_support_draw`` — a money ledger that can
    never be overdrawn and never re-prices past draws."""

    def _remaining(self, user):
        # What production reads: the engine's per-member remaining hours.
        budget = self.job.get_support_budget()
        return budget["per_member"][user.id]["remaining_hours"]

    def _draw(self, role, hours, start=date(2026, 9, 1), end=date(2026, 9, 7)):
        return create_support_draw(
            role, start, end, Decimal(str(hours)), created_by=self.root
        )

    def test_draws_reduce_remaining_and_carry_forward(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)  # budget_money 800 -> 16h @50
        self.assertEqual(self._remaining(u), Decimal("16"))

        self._draw(role, 5)
        self._draw(role, 4, start=date(2026, 9, 8), end=date(2026, 9, 14))
        self.assertEqual(role.drawn_hours(), Decimal("9"))
        self.assertEqual(self._remaining(u), Decimal("7"))

    def test_draw_records_lcr_and_money(self):
        u = self._user(1, lcr=50)
        d = self._draw(self._role(u, 100), 3)
        self.assertEqual(d.lcr_at_draw, Decimal("50"))
        self.assertEqual(d.money_drawn, Decimal("150.00"))

    def test_over_draw_rejected(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        with self.assertRaises(ValidationError):
            self._draw(role, 20)
        self._draw(role, 16)  # exactly the budget is fine
        with self.assertRaises(ValidationError):
            self._draw(role, Decimal("0.01"))
        self.assertEqual(role.draws.count(), 1)

    def test_zero_negative_and_reversed_rejected(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        for hours in (0, -5):
            with self.assertRaises(ValidationError):
                self._draw(role, hours)
        with self.assertRaises(ValidationError):
            self._draw(role, 1, start=date(2026, 9, 10), end=date(2026, 9, 1))
        self.assertFalse(role.draws.exists())

    def test_no_lcr_cannot_draw(self):
        u = self._user(1)  # no cost rate
        with self.assertRaises(ValidationError):
            self._draw(self._role(u, 100), 1)

    def test_lcr_rise_does_not_reprice_past_draws(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)  # £800
        self._draw(role, 16)  # all £800 drawn at £50/h
        UserCost.objects.create(
            user=u, effective_from=date(2021, 1, 1), cost_per_hour=Decimal("100")
        )
        m = self.job.get_support_budget()["per_member"][u.id]
        self.assertEqual(m["remaining_money"], Decimal("0"))
        self.assertEqual(m["remaining_hours"], Decimal("0"))  # not -8

    def test_lcr_rise_values_remaining_at_new_rate(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)  # £800
        self._draw(role, 8)  # £400 left
        UserCost.objects.create(
            user=u, effective_from=date(2021, 1, 1), cost_per_hour=Decimal("100")
        )
        self.assertEqual(self._remaining(u), Decimal("4"))  # £400 @ £100

    def test_drawable_statuses(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        for status in (JobStatuses.DELETED, JobStatuses.ARCHIVED, JobStatuses.LOST):
            Job.objects.filter(pk=self.job.pk).update(status=status)
            with self.assertRaises(ValidationError):
                self._draw(role, 1)
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.COMPLETED)
        self._draw(role, 1)
        self.assertEqual(role.draws.count(), 1)

    def test_sentinel_and_null_rows_excluded_from_split(self):
        u = self._user(1, lcr=50)
        self._role(u, 100)
        JobSupportTeamRole.objects.create(job=self.job, user=None)
        JobSupportTeamRole.objects.create(job=self.job, user=get_sentinel_user())
        b = self.job.get_support_budget()
        self.assertEqual(b["percent_sum"], Decimal("100"))
        self.assertEqual(b["per_member"][u.id]["budget_money"], Decimal("800"))
        self.assertTrue(b["warnings"])

    def test_draw_denormalises_user(self):
        u = self._user(1, lcr=50)
        d = self._draw(self._role(u, 100), 1)
        self.assertEqual(d.user_id, u.id)

    def test_user_rollup_period_filter(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        self._draw(role, 3)
        roll = build_user_support_budget(
            u, start=date(2026, 9, 1), end=date(2026, 9, 30)
        )
        self.assertEqual(len(roll["per_job"]), 1)
        entry = roll["per_job"][0]
        self.assertEqual(entry["period_drawn_hours"], Decimal("3"))
        self.assertEqual(entry["remaining_hours"], Decimal("13"))  # 16 - 3
        self.assertTrue(roll["has_remaining"])

    def test_user_rollup_includes_completed_jobs(self):
        u = self._user(1, lcr=50)
        self._role(u, 100)
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.COMPLETED)
        self.assertEqual(len(build_user_support_budget(u)["per_job"]), 1)
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.ARCHIVED)
        self.assertEqual(len(build_user_support_budget(u)["per_job"]), 0)

    def test_auto_cash_out_tops_up_partial_draw(self):
        u = self._user(1, lcr=50)
        role = self._role(u, 100)
        self._draw(role, 1, start=date(2026, 9, 1), end=date(2026, 9, 14))
        created = auto_cash_out(u, date(2026, 9, 1), date(2026, 9, 14), self.root)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].hours_drawn, Decimal("15.00"))
        # Nothing left — a second run creates nothing.
        self.assertEqual(
            auto_cash_out(u, date(2026, 9, 1), date(2026, 9, 14), self.root), []
        )
        self.assertEqual(role.drawn_hours(), Decimal("16"))


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
        self.assertIn(self.owner.get_absolute_url(), body)  # person column is populated
        self.assertIn("Budget (h)", body)

    def test_sales_dashboard_hides_hours_without_finance_perm(self):
        # Hours + revenue x premium x share would reveal the member's LCR.
        viewer = User.objects.create_user(email="viewer@test.com", password="pw")
        assign_perm("jobtracker.can_view_jobs", viewer, self.unit)
        self.http.force_login(viewer)
        resp = self.http.get(reverse("view_job_sales", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("Budget (h)", body)
        self.assertNotIn("16.0", body)

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

    def test_view_rejects_overdraw(self):
        self.http.force_login(self.owner)
        resp = self.http.post(
            self._draw_url(),
            {"period_start": "2026-09-01", "period_end": "2026-09-14", "hours_drawn": "17"},
        )
        body = resp.json()
        self.assertFalse(body["form_is_valid"])
        self.assertIn("hours_drawn", body["form_errors"])
        self.assertFalse(self.role.draws.exists())

    def test_view_rejects_reversed_period_and_negative(self):
        self.http.force_login(self.owner)
        for payload in (
            {"period_start": "2026-09-14", "period_end": "2026-09-01", "hours_drawn": "1"},
            {"period_start": "2026-09-01", "period_end": "2026-09-14", "hours_drawn": "-1"},
        ):
            self.assertFalse(self.http.post(self._draw_url(), payload).json()["form_is_valid"])
        self.assertFalse(self.role.draws.exists())

    def test_get_prefill_ignores_period_for_lcr(self):
        # A cheaper historic rate must not inflate the pre-filled hours.
        UserCost.objects.create(
            user=self.owner, effective_from=date(2010, 1, 1), cost_per_hour=Decimal("10")
        )
        self.http.force_login(self.owner)
        resp = self.http.get(self._draw_url() + "?start=2015-01-01&end=2015-01-14")
        self.assertIn('value="16.00"', resp.json()["html_form"])

    def test_auto_cash_out_never_exceeds_remaining(self):
        self.http.force_login(self.owner)
        url = reverse("user_support_auto_draw", kwargs={"email": self.owner.email})
        self.http.post(url, {"start": "2026-09-01", "end": "2026-09-14"})
        self.http.post(url, {"start": "2026-09-15", "end": "2026-09-30"})
        self.assertEqual(self.role.drawn_hours(), Decimal("16.00"))

    def test_job_page_draw_requires_schedule_perm_and_is_limited(self):
        url = reverse(
            "job_support_team_draw", kwargs={"slug": self.job.slug, "pk": self.role.pk}
        )
        payload = {"period_start": "2026-09-01", "period_end": "2026-09-14", "hours_drawn": "2"}
        self.http.force_login(self.stranger)
        self.assertEqual(self.http.post(url, payload).status_code, 403)

        self.http.force_login(self.root)  # sole first user -> superuser
        self.root.is_superuser = True
        self.root.save()
        self.assertTrue(self.http.post(url, payload).json()["form_is_valid"])
        payload["hours_drawn"] = "15"
        self.assertFalse(self.http.post(url, payload).json()["form_is_valid"])
        self.assertEqual(self.role.drawn_hours(), Decimal("2"))

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
        self.profile = SupportProfile.objects.create(unit=self.unit, name="Context")
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
            (
                "organisationalunit_support_template_add",
                {"slug": self.unit.slug, "profile_pk": self.profile.pk},
            ),
            ("organisationalunit_support_profile_add", {"slug": self.unit.slug}),
            (
                "organisationalunit_support_profile_edit",
                {"slug": self.unit.slug, "pk": self.profile.pk},
            ),
            (
                "organisationalunit_support_profile_delete",
                {"slug": self.unit.slug, "pk": self.profile.pk},
            ),
            ("organisationalunit_set_lcr", {"slug": self.unit.slug, "member_pk": self.membership.pk}),
        ]:
            resp = self.http.get(reverse(name, kwargs=kwargs))
            self.assertEqual(resp.status_code, 403, name)

    def test_add_template_member_and_set_lcr(self):
        self.http.force_login(self.finance)
        # Add a template member.
        resp = self.http.post(
            reverse(
                "organisationalunit_support_template_add",
                kwargs={"slug": self.unit.slug, "profile_pk": self.profile.pk},
            ),
            {"user": self.member_user.pk, "role": 0, "profile_percent": "100"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertTrue(
            OrganisationalUnitSupportTemplateMember.objects.filter(
                profile=self.profile, unit=self.unit, user=self.member_user
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


class SupportIntegrityTests(SupportBudgetTestBase):
    """Uniqueness, PROTECTed cash-outs, validators and draw reversal."""

    def setUp(self):
        super().setUp()
        self.root.is_superuser = True
        self.root.save()
        self.member = self._user(1, lcr=50)
        self.role = self._role(self.member, 100)  # £800 -> 16h
        self.stranger = self._user(2)
        self.http = TestHttpClient(HTTP_HOST="localhost")

    def _draw(self, hours=4):
        return create_support_draw(
            self.role, date(2026, 9, 1), date(2026, 9, 14), Decimal(str(hours)),
            created_by=self.member,
        )

    def test_duplicate_member_rejected_by_add_view(self):
        self.http.force_login(self.root)
        resp = self.http.post(
            reverse("job_support_team_add", kwargs={"slug": self.job.slug}),
            {"user": self.member.pk, "role": 0, "profile_percent": "50"},
        )
        self.assertFalse(resp.json()["form_is_valid"])
        self.assertEqual(self.job.supporting_team.count(), 1)

    def test_negative_percent_rejected(self):
        from jobtracker.forms import JobSupportTeamRoleForm

        form = JobSupportTeamRoleForm(
            {"user": self.stranger.pk, "role": 0, "profile_percent": "-10"}, job=self.job
        )
        self.assertFalse(form.is_valid())
        self.assertIn("profile_percent", form.errors)

    def test_duplicate_template_member_is_form_error(self):
        from jobtracker.forms import SupportTemplateMemberForm

        tm = OrganisationalUnitSupportTemplateMember.objects.create(
            unit=self.unit, user=self.member
        )
        form = SupportTemplateMemberForm(
            {"user": self.member.pk, "role": 0, "profile_percent": "100"},
            profile=tm.profile,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("user", form.errors)

    def test_role_with_draws_cannot_be_deleted(self):
        self._draw()
        self.http.force_login(self.root)
        resp = self.http.post(
            reverse(
                "job_support_team_delete",
                kwargs={"slug": self.job.slug, "pk": self.role.pk},
            ),
            {"user_action": "approve_action"},
        )
        self.assertFalse(resp.json()["form_is_valid"])
        self.assertTrue(JobSupportTeamRole.objects.filter(pk=self.role.pk).exists())

    def test_user_locked_on_role_with_draws(self):
        from jobtracker.forms import JobSupportTeamRoleForm

        self._draw()
        form = JobSupportTeamRoleForm(
            {"user": self.stranger.pk, "role": 0, "profile_percent": "100"},
            instance=self.role,
            job=self.job,
        )
        self.assertTrue(form.fields["user"].disabled)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.save().user_id, self.member.id)

    def _history_url(self):
        return reverse(
            "job_support_team_draws", kwargs={"slug": self.job.slug, "pk": self.role.pk}
        )

    def _reverse_url(self, draw):
        return reverse(
            "job_support_team_draw_delete",
            kwargs={"slug": self.job.slug, "pk": self.role.pk, "draw_pk": draw.pk},
        )

    def test_history_visible_to_member_not_stranger(self):
        self._draw()
        self.http.force_login(self.member)
        resp = self.http.get(self._history_url())
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Reverse</button>", resp.json()["html_form"])
        self.http.force_login(self.stranger)
        self.assertEqual(self.http.get(self._history_url()).status_code, 403)

    def test_member_cannot_reverse_own_draw(self):
        draw = self._draw()
        self.http.force_login(self.member)
        resp = self.http.post(self._reverse_url(draw), {"user_action": "approve_action"})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(self.role.draws.exists())

    def test_scheduler_reverses_draw_and_budget_returns(self):
        draw = self._draw(4)
        self.http.force_login(self.root)
        self.assertIn("Reverse</button>", self.http.get(self._history_url()).json()["html_form"])
        resp = self.http.post(self._reverse_url(draw), {"user_action": "approve_action"})
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertFalse(self.role.draws.exists())
        m = self.job.get_support_budget()["per_member"][self.member.id]
        self.assertEqual(m["remaining_hours"], Decimal("16"))


class SupportProfileTests(SupportBudgetTestBase):
    """Multiple named support profiles per unit (e.g. UKI Context vs CCX)."""

    def setUp(self):
        super().setUp()
        self.a = self._user(1, lcr=50)
        self.b = self._user(2, lcr=50)
        self.c = self._user(3, lcr=50)
        self.context = SupportProfile.objects.create(unit=self.unit, name="Context")
        self.ccx = SupportProfile.objects.create(
            unit=self.unit, name="CCX", premium_percent=Decimal("4")
        )
        for user, profile in ((self.a, self.context), (self.b, self.context),
                              (self.a, self.ccx), (self.c, self.ccx)):
            OrganisationalUnitSupportTemplateMember.objects.create(
                profile=profile, user=user, profile_percent=Decimal("100")
            )

    def _new_job(self):
        return Job.objects.create(
            title="New", client=self.client_obj, unit=self.unit,
            created_by=self.root, account_manager=self.root, revenue=Decimal("10000"),
        )

    def test_first_profile_is_default_and_only_one_default(self):
        self.context.refresh_from_db()
        self.ccx.refresh_from_db()
        self.assertTrue(self.context.is_default)
        self.assertFalse(self.ccx.is_default)
        self.ccx.is_default = True
        self.ccx.save()
        self.context.refresh_from_db()
        self.assertFalse(self.context.is_default)
        self.assertEqual(self.unit.get_default_support_profile(), self.ccx)

    def test_deleting_default_promotes_another(self):
        self.context.delete()
        self.ccx.refresh_from_db()
        self.assertTrue(self.ccx.is_default)

    def test_same_person_in_two_profiles(self):
        self.assertEqual(
            OrganisationalUnitSupportTemplateMember.objects.filter(user=self.a).count(), 2
        )

    def test_new_job_gets_default_profile(self):
        job = self._new_job()
        job.refresh_from_db()
        self.assertEqual(job.support_profile, self.context)
        self.assertEqual(
            set(job.supporting_team.values_list("user_id", flat=True)),
            {self.a.id, self.b.id},
        )
        self.assertEqual(job.get_effective_premium(), Decimal("8"))  # unit default

    def test_profile_premium_precedence(self):
        self.context.apply_to_job(self.job)
        self.ccx.apply_to_job(self.job, replace=True)
        self.job.refresh_from_db()
        self.assertEqual(self.job.get_effective_premium(), Decimal("4"))
        b = self.job.get_support_budget()
        self.assertEqual(b["pool"], Decimal("400"))
        self.job.support_premium_override = Decimal("10")
        self.assertEqual(self.job.get_effective_premium(), Decimal("10"))

    def test_switch_with_replace_keeps_rows_with_cash_outs(self):
        self.context.apply_to_job(self.job)
        role_b = JobSupportTeamRole.objects.get(job=self.job, user=self.b)
        create_support_draw(role_b, date(2026, 9, 1), date(2026, 9, 14), Decimal("1"))
        summary = self.ccx.apply_to_job(self.job, replace=True)
        self.assertEqual(summary["created"], 1)  # c
        self.assertEqual(summary["retained"], 1)  # b has a cash-out
        self.assertEqual(
            set(self.job.supporting_team.values_list("user_id", flat=True)),
            {self.a.id, self.b.id, self.c.id},
        )
        self.context.apply_to_job(self.job, replace=True)
        self.assertFalse(self.job.supporting_team.filter(user=self.c).exists())

    def test_switch_without_replace_keeps_everyone(self):
        self.context.apply_to_job(self.job)
        self.ccx.apply_to_job(self.job)
        self.assertEqual(self.job.supporting_team.count(), 3)

    def test_unit_only_member_lands_in_default_profile(self):
        d = self._user(4)
        tm = OrganisationalUnitSupportTemplateMember.objects.create(unit=self.unit, user=d)
        self.assertEqual(tm.profile, self.context)

    def test_change_profile_view(self):
        self.root.is_superuser = True
        self.root.save()
        http = TestHttpClient(HTTP_HOST="localhost")
        http.force_login(self.root)
        url = reverse("job_support_team_apply_template", kwargs={"slug": self.job.slug})
        resp = http.get(url)
        self.assertIn("Premium override", resp.json()["html_form"])
        resp = http.post(
            url,
            {"profile": self.ccx.pk, "replace": "on", "support_premium_override": "6"},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.job.refresh_from_db()
        self.assertEqual(self.job.support_profile, self.ccx)
        self.assertEqual(self.job.support_premium_override, Decimal("6"))
        self.assertEqual(
            set(self.job.supporting_team.values_list("user_id", flat=True)),
            {self.a.id, self.c.id},
        )

    def test_change_profile_view_premium_needs_finance_perm(self):
        scheduler = self._user(9)
        assign_perm("jobtracker.can_schedule_job", scheduler, self.unit)
        assign_perm("jobtracker.can_view_jobs", scheduler, self.unit)
        http = TestHttpClient(HTTP_HOST="localhost")
        http.force_login(scheduler)
        url = reverse("job_support_team_apply_template", kwargs={"slug": self.job.slug})
        resp = http.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Premium override", resp.json()["html_form"])
        resp = http.post(url, {"profile": self.ccx.pk, "support_premium_override": "50"})
        self.assertTrue(resp.json()["form_is_valid"])
        self.job.refresh_from_db()
        self.assertEqual(self.job.support_profile, self.ccx)
        self.assertIsNone(self.job.support_premium_override)

    def test_profile_from_other_unit_rejected(self):
        other_unit = OrganisationalUnit.objects.create(name="Other")
        foreign = SupportProfile.objects.create(unit=other_unit, name="Foreign")
        self.root.is_superuser = True
        self.root.save()
        http = TestHttpClient(HTTP_HOST="localhost")
        http.force_login(self.root)
        resp = http.post(
            reverse("job_support_team_apply_template", kwargs={"slug": self.job.slug}),
            {"profile": foreign.pk},
        )
        self.assertFalse(resp.json()["form_is_valid"])

    def test_finance_tab_profile_crud(self):
        fin = self._user(8)
        assign_perm("jobtracker.view_organisationalunit", fin, self.unit)
        assign_perm("jobtracker.can_view_loaded_costs", fin, self.unit)
        http = TestHttpClient(HTTP_HOST="localhost")
        http.force_login(fin)
        resp = http.post(
            reverse("organisationalunit_support_profile_add", kwargs={"slug": self.unit.slug}),
            {"name": "Ops", "premium_percent": "3"},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        ops = SupportProfile.objects.get(unit=self.unit, name="Ops")
        # Duplicate name is a form error.
        resp = http.post(
            reverse("organisationalunit_support_profile_add", kwargs={"slug": self.unit.slug}),
            {"name": "ops"},
        )
        self.assertFalse(resp.json()["form_is_valid"])
        resp = http.post(
            reverse(
                "organisationalunit_support_profile_edit",
                kwargs={"slug": self.unit.slug, "pk": ops.pk},
            ),
            {"name": "Ops", "premium_percent": "3", "is_default": "on"},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertEqual(self.unit.get_default_support_profile(), ops)
        body = http.get(
            reverse("organisationalunit_detail", kwargs={"slug": self.unit.slug})
        ).content.decode()
        self.assertIn("Support Profiles", body)
        self.assertIn("CCX", body)
        resp = http.post(
            reverse(
                "organisationalunit_support_profile_delete",
                kwargs={"slug": self.unit.slug, "pk": ops.pk},
            ),
            {"user_action": "approve_action"},
        )
        self.assertTrue(resp.json()["form_is_valid"])
        self.assertFalse(SupportProfile.objects.filter(pk=ops.pk).exists())


class CashOutRulesTests(SupportBudgetTestBase):
    """Server-side cash-out rules: never overdraw (all three entry points),
    scheduling rights alone don't cash out someone else's budget, and only
    current/past periods can be cashed out."""

    def setUp(self):
        super().setUp()
        self.member = self._user(1, lcr=50)
        self.role = self._role(self.member, 100)  # £800 -> 16h
        self.manager = self._user(2)
        self.member.manager = self.manager
        self.member.save()
        self.scheduler = self._user(3)
        self.finance = self._user(4)
        for u in (self.scheduler, self.manager, self.finance):
            assign_perm("jobtracker.can_schedule_job", u, self.unit)
            assign_perm("jobtracker.can_view_jobs", u, self.unit)
        assign_perm("jobtracker.can_view_loaded_costs", self.finance, self.unit)
        self.http = TestHttpClient(HTTP_HOST="localhost")

    def _job_url(self):
        return reverse(
            "job_support_team_draw", kwargs={"slug": self.job.slug, "pk": self.role.pk}
        )

    def _user_url(self):
        return reverse(
            "user_support_draw",
            kwargs={"email": self.member.email, "role_pk": self.role.pk},
        )

    def _payload(self, hours, start="2026-09-01", end="2026-09-14"):
        return {"period_start": start, "period_end": end, "hours_drawn": str(hours)}

    def test_overdraw_rejected_job_page(self):
        self.http.force_login(self.finance)
        body = self.http.post(self._job_url(), self._payload(17)).json()
        self.assertFalse(body["form_is_valid"])
        self.assertFalse(self.role.draws.exists())

    def test_overdraw_rejected_user_page(self):
        self.http.force_login(self.member)
        body = self.http.post(self._user_url(), self._payload(17)).json()
        self.assertFalse(body["form_is_valid"])
        self.assertFalse(self.role.draws.exists())

    def test_auto_draw_caps_at_remaining(self):
        create_support_draw(
            self.role, date(2026, 9, 1), date(2026, 9, 7), Decimal("10"), self.member
        )
        self.http.force_login(self.member)
        self.http.post(
            reverse("user_support_auto_draw", kwargs={"email": self.member.email}),
            {"start": "2026-09-08", "end": "2026-09-14"},
        )
        self.assertEqual(self.role.drawn_hours(), Decimal("16"))

    def test_scheduler_cannot_cash_out_others(self):
        self.http.force_login(self.scheduler)
        self.assertEqual(self.http.get(self._job_url()).status_code, 403)
        self.assertEqual(
            self.http.post(self._job_url(), self._payload(2)).status_code, 403
        )
        self.assertFalse(self.role.draws.exists())
        # ...and the menu item is hidden for them.
        resp = self.http.get(reverse("job_detail", kwargs={"slug": self.job.slug}))
        self.assertNotIn('"%s"' % self._job_url(), resp.content.decode())

    def test_manager_and_finance_can_cash_out_on_job_page(self):
        for u in (self.manager, self.finance):
            self.http.force_login(u)
            self.assertTrue(
                self.http.post(self._job_url(), self._payload(2)).json()["form_is_valid"]
            )
        self.assertEqual(self.role.drawn_hours(), Decimal("4"))
        resp = self.http.get(reverse("job_detail", kwargs={"slug": self.job.slug}))
        self.assertIn('"%s"' % self._job_url(), resp.content.decode())

    def test_future_period_rejected(self):
        from datetime import timedelta

        start = date.today() + timedelta(days=1)
        end = start + timedelta(days=6)
        with self.assertRaises(ValidationError):
            create_support_draw(self.role, start, end, Decimal("1"), self.member)
        self.http.force_login(self.member)
        body = self.http.post(
            self._user_url(), self._payload(1, start.isoformat(), end.isoformat())
        ).json()
        self.assertFalse(body["form_is_valid"])
        self.http.post(
            reverse("user_support_auto_draw", kwargs={"email": self.member.email}),
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        self.assertFalse(self.role.draws.exists())

    def test_current_period_allowed(self):
        from chaotica_utils.utils import period_for_date

        start, end = period_for_date(date.today())
        create_support_draw(self.role, start, end, Decimal("1"), self.member)
        self.assertEqual(self.role.draws.count(), 1)


class SupportRoleFormTests(SupportBudgetTestBase):
    """The support-role picker is an AJAX user search over live users only."""

    def test_user_required(self):
        from jobtracker.forms import JobSupportTeamRoleForm

        form = JobSupportTeamRoleForm({"role": 0, "profile_percent": "100"}, job=self.job)
        self.assertFalse(form.is_valid())
        self.assertIn("user", form.errors)

    def test_inactive_and_sentinel_excluded(self):
        from jobtracker.forms import JobSupportTeamRoleForm

        gone = self._user(1)
        gone.is_active = False
        gone.save()
        for u in (gone, get_sentinel_user()):
            form = JobSupportTeamRoleForm(
                {"user": u.pk, "role": 0, "profile_percent": "100"}, job=self.job
            )
            self.assertFalse(form.is_valid())
            self.assertIn("user", form.errors)

    def test_edit_keeps_deactivated_member_selected(self):
        from jobtracker.forms import JobSupportTeamRoleForm

        u = self._user(1)
        role = self._role(u, 100)
        u.is_active = False
        u.save()
        form = JobSupportTeamRoleForm(instance=role, job=self.job)
        self.assertIn('value="%d" selected' % u.pk, str(form["user"]))

    def test_modal_uses_ajax_search(self):
        self.root.is_superuser = True
        self.root.save()
        http = TestHttpClient(HTTP_HOST="localhost")
        http.force_login(self.root)
        html = http.get(
            reverse("job_support_team_add", kwargs={"slug": self.job.slug})
        ).json()["html_form"]
        self.assertIn('data-ajax--url="/autocomplete/users"', html)
        self.assertIn("dropdownParent", html)
        self.assertIn("Add Support Role", html)
        # Not a full user list: no option per user.
        self._user(9)
        html = http.get(
            reverse("job_support_team_add", kwargs={"slug": self.job.slug})
        ).json()["html_form"]
        self.assertNotIn("u9@test.com", html)
        role = self._role(self._user(10), 50)
        html = http.get(
            reverse(
                "job_support_team_edit", kwargs={"slug": self.job.slug, "pk": role.pk}
            )
        ).json()["html_form"]
        self.assertIn("Edit Support Role", html)
