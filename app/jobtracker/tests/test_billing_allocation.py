"""Tests for billing-code assignments, phase-override resolution and the
per-user code-allocation engine.

Business-hour totals depend on the working calendar, so the ``slot_daily_hours``
tests assert internal *consistency* (per-day sum equals the whole-slot total)
rather than brittle absolute hour counts.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

from constance.test import override_config
from django.test import TestCase, Client as TestHttpClient
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import User
from chaotica_utils.utils import (
    code_applies_on,
    slot_daily_hours,
    build_user_code_allocation,
)
from jobtracker.models import (
    Client,
    Job,
    Phase,
    OrganisationalUnit,
    TimeSlot,
    TimeSlotType,
    BillingCode,
    BillingCodeAssignment,
)
from jobtracker.enums import (
    DefaultTimeSlotTypes,
    PhaseStatuses,
    TimeSlotDeliveryRole,
)


def _monday(base):
    return (base - timedelta(days=base.weekday())).replace(
        hour=9, minute=0, second=0, microsecond=0
    )


class CodeAppliesOnTests(TestCase):
    def _a(self, start, end):
        return BillingCodeAssignment(start_date=start, end_date=end)

    def test_undated_always_applies(self):
        self.assertTrue(code_applies_on(self._a(None, None), date(2026, 1, 1)))

    def test_closed_range_boundaries(self):
        a = self._a(date(2026, 1, 10), date(2026, 1, 20))
        self.assertFalse(code_applies_on(a, date(2026, 1, 9)))
        self.assertTrue(code_applies_on(a, date(2026, 1, 10)))  # inclusive start
        self.assertTrue(code_applies_on(a, date(2026, 1, 20)))  # inclusive end
        self.assertFalse(code_applies_on(a, date(2026, 1, 21)))

    def test_open_ended_bounds(self):
        self.assertTrue(
            code_applies_on(self._a(None, date(2026, 1, 20)), date(2020, 1, 1))
        )
        self.assertTrue(
            code_applies_on(self._a(date(2026, 1, 10), None), date(2030, 1, 1))
        )


class BillingAllocationTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser(email="root@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="Unit")
        self.client_obj = Client.objects.create(name="Acme")
        self.other_client = Client.objects.create(name="Globex")
        self.user = User.objects.create_user(email="u1@test.com", password="pw")

        self.delivery_type = TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.DELIVERY
        )

        self.job = Job.objects.create(
            title="Test job", client=self.client_obj, unit=self.unit,
            created_by=self.root, account_manager=self.root,
        )
        self.phase = Phase.objects.create(
            job=self.job, title="P1",
            status=PhaseStatuses.SCHEDULED_CONFIRMED,
        )
        self.code_a = BillingCode.objects.create(
            code="A-1", client=self.client_obj, is_chargeable=True
        )
        self.code_b = BillingCode.objects.create(
            code="B-1", client=self.client_obj, is_chargeable=True
        )

    def _slot(self, start, end):
        return TimeSlot.objects.create(
            user=self.user,
            slot_type=self.delivery_type,
            phase=self.phase,
            start=start,
            end=end,
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
        )

    # --- override resolution ---------------------------------------------

    def test_phase_inherits_job_codes_when_no_own(self):
        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        eff = self.phase.get_effective_billing_assignments()
        self.assertEqual([a.code_id for a in eff], [self.code_a.id])
        self.assertFalse(self.phase.has_own_billing_assignments())

    def test_phase_own_codes_override_job(self):
        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        BillingCodeAssignment.objects.create(code=self.code_b, phase=self.phase)
        eff = self.phase.get_effective_billing_assignments()
        self.assertEqual([a.code_id for a in eff], [self.code_b.id])
        self.assertTrue(self.phase.has_own_billing_assignments())

    # --- slot_daily_hours -------------------------------------------------

    def test_single_day_equals_get_business_hours(self):
        start = _monday(timezone.now())
        slot = self._slot(start, start.replace(hour=17, minute=30))
        daily = slot_daily_hours(slot)
        self.assertEqual(len(daily), 1)
        self.assertEqual(sum(daily.values()), slot.get_business_hours())

    def test_multi_day_sum_equals_whole_slot(self):
        monday = _monday(timezone.now())
        # Monday 09:00 -> Wednesday 17:30
        end = (monday + timedelta(days=2)).replace(hour=17, minute=30)
        slot = self._slot(monday, end)
        daily = slot_daily_hours(slot)
        self.assertGreater(len(daily), 1)
        self.assertEqual(sum(daily.values()), slot.get_business_hours())

    def test_window_clips_out_of_range_days_without_changing_hours(self):
        """A window restricts which days are returned but not their hours.

        Guards the analytics/allocation fast path: clipping a long slot to the
        requested window must yield exactly the in-window subset of the full
        per-day result (same days, same hours), never a recomputed value.
        """
        monday = _monday(timezone.now())
        # Monday 09:00 -> Friday 17:30 (a full working week).
        end = (monday + timedelta(days=4)).replace(hour=17, minute=30)
        slot = self._slot(monday, end)

        full = slot_daily_hours(slot)
        # Window covering only Tuesday..Wednesday.
        win_start = (monday + timedelta(days=1)).date()
        win_end = (monday + timedelta(days=2)).date()
        clipped = slot_daily_hours(slot, window_start=win_start, window_end=win_end)

        self.assertEqual(
            set(clipped), {d for d in full if win_start <= d <= win_end}
        )
        for day, hours in clipped.items():
            self.assertEqual(hours, full[day])

    def test_window_outside_slot_returns_empty(self):
        monday = _monday(timezone.now())
        slot = self._slot(monday, monday.replace(hour=17, minute=30))
        after = (monday + timedelta(days=10)).date()
        self.assertEqual(
            slot_daily_hours(slot, window_start=after, window_end=after), {}
        )

    # --- build_user_code_allocation --------------------------------------

    def test_multi_code_day_keeps_all_matches(self):
        # An undated code plus a dated code that also covers the slot day.
        monday = _monday(timezone.now())
        slot = self._slot(monday, monday.replace(hour=17, minute=30))
        day = monday.date()
        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        BillingCodeAssignment.objects.create(
            code=self.code_b, job=self.job,
            start_date=day - timedelta(days=1), end_date=day + timedelta(days=1),
        )
        alloc = build_user_code_allocation(
            self.user, day - timedelta(days=2), day + timedelta(days=2)
        )
        code_ids = {e["code_id"] for e in alloc["per_day"][day]}
        self.assertEqual(code_ids, {self.code_a.id, self.code_b.id})
        self.assertEqual(set(alloc["per_code"]), {self.code_a.id, self.code_b.id})

    def test_split_policy_divides_across_codes(self):
        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        BillingCodeAssignment.objects.create(code=self.code_b, job=self.job)
        monday = _monday(timezone.now())
        self._slot(monday, monday.replace(hour=17))
        day = monday.date()
        with override_config(BILLING_DUPLICATE_CODE_POLICY="split"):
            split = build_user_code_allocation(self.user, day, day)
        s = {e["code_id"]: e["hours"] for e in split["per_day"][day] if e["code"]}
        self.assertEqual(s[self.code_a.id], s[self.code_b.id])  # even split
        with override_config(BILLING_DUPLICATE_CODE_POLICY="stack"):
            stacked = build_user_code_allocation(self.user, day, day)
        st = {e["code_id"]: e["hours"] for e in stacked["per_day"][day] if e["code"]}
        self.assertEqual(s[self.code_a.id] * 2, st[self.code_a.id])

    def test_prefer_newest_picks_one_code(self):
        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        BillingCodeAssignment.objects.create(code=self.code_b, job=self.job)  # newer
        monday = _monday(timezone.now())
        self._slot(monday, monday.replace(hour=17))
        day = monday.date()
        with override_config(BILLING_DUPLICATE_CODE_POLICY="prefer_newest"):
            alloc = build_user_code_allocation(self.user, day, day)
        coded = {e["code_id"] for e in alloc["per_day"][day] if e["code"]}
        self.assertEqual(coded, {self.code_b.id})

    def test_leave_wins_zeroes_coded_day(self):
        from jobtracker.models import TimeSlotType
        from jobtracker.enums import DefaultTimeSlotTypes

        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        monday = _monday(timezone.now())
        self._slot(monday, monday.replace(hour=17))  # delivery
        leave_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.LEAVE)
        TimeSlot.objects.create(
            user=self.user, slot_type=leave_type,
            start=monday, end=monday.replace(hour=17),
        )
        day = monday.date()
        alloc = build_user_code_allocation(self.user, day, day)
        coded = [e for e in alloc["per_day"][day] if e["code"]]
        self.assertEqual(coded, [])  # leave wins — the overran day isn't coded
        self.assertEqual(alloc["stats"]["coded_hours"], 0)
        self.assertGreater(alloc["stats"]["unavailable_hours"], 0)
        # A leave entry is still shown for the day.
        kinds = {e["kind"] for e in alloc["per_day"][day] if not e["code"]}
        self.assertIn("unavailable", kinds)

    def test_stats_capacity_is_business_days(self):
        # A single weekday -> capacity = 1 day * hours-per-day (7.5 default).
        monday = _monday(timezone.now())
        day = monday.date()
        alloc = build_user_code_allocation(self.user, day, day)
        self.assertEqual(alloc["stats"]["capacity_hours"], Decimal("7.5"))

    def test_support_draw_overlays_as_timesheet(self):
        from decimal import Decimal
        from jobtracker.models import JobSupportTeamRole, SupportBudgetDraw

        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        role = JobSupportTeamRole.objects.create(
            job=self.job, user=self.user, profile_percent=Decimal("100")
        )
        monday = _monday(timezone.now()).date()
        friday = monday + timedelta(days=4)  # Mon–Fri, 5 working days
        SupportBudgetDraw.objects.create(
            support_role=role, user=self.user,
            period_start=monday, period_end=friday,
            hours_drawn=Decimal("10"), created_by=self.root,
        )
        alloc = build_user_code_allocation(self.user, monday, friday)
        self.assertEqual(alloc["stats"]["support_hours"], Decimal("10"))
        self.assertIn(self.code_a.id, alloc["per_code"])  # code from the draw
        support_entries = [
            e for day in alloc["per_day"].values()
            for e in day if e.get("kind") == "support"
        ]
        self.assertTrue(support_entries)
        self.assertEqual(support_entries[0]["code"].id, self.code_a.id)

    def test_coded_day_includes_phase_target(self):
        # Each coded per-day entry carries the phase/project the hours were on.
        BillingCodeAssignment.objects.create(code=self.code_a, job=self.job)
        monday = _monday(timezone.now())
        self._slot(monday, monday.replace(hour=17))
        alloc = build_user_code_allocation(
            self.user, monday.date(), monday.date()
        )
        entries = alloc["per_day"][monday.date()]
        coded = [e for e in entries if e["code"]]
        self.assertTrue(coded)
        targets = coded[0]["targets"]
        self.assertEqual(targets[0]["kind"], "phase")
        self.assertEqual(targets[0]["label"], str(self.phase))
        self.assertEqual(targets[0]["hours"], coded[0]["hours"])

    def test_assign_modals_render(self):
        from jobtracker.models import Project

        project = Project.objects.create(
            title="Proj", client=self.client_obj, created_by=self.root
        )
        http = TestHttpClient(HTTP_HOST="localhost")
        http.force_login(self.root)  # superuser bypasses object perms
        targets = [
            reverse("assign_job_billingcodes", kwargs={"slug": self.job.slug}),
            reverse(
                "assign_phase_billingcodes",
                kwargs={"job_slug": self.job.slug, "slug": self.phase.slug},
            ),
            reverse("assign_project_billingcodes", kwargs={"slug": project.slug}),
        ]
        for url in targets:
            resp = http.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertIn("html_form", resp.json(), url)

    def test_dated_code_excluded_outside_range(self):
        monday = _monday(timezone.now())
        slot = self._slot(monday, monday.replace(hour=17, minute=30))
        day = monday.date()
        BillingCodeAssignment.objects.create(
            code=self.code_b, job=self.job,
            start_date=day + timedelta(days=10), end_date=day + timedelta(days=20),
        )
        alloc = build_user_code_allocation(
            self.user, day - timedelta(days=2), day + timedelta(days=2)
        )
        # The code doesn't apply in-window, so it contributes no coded hours...
        self.assertEqual(alloc["per_code"], {})
        # ...but the scheduled work is surfaced as uncoded, not silently dropped.
        self.assertIn(day, alloc["per_day"])
        self.assertTrue(all(e["code"] is None for e in alloc["per_day"][day]))
        self.assertGreater(alloc["uncoded"]["hours"], 0)

    def test_uncoded_slot_is_surfaced(self):
        # A scheduled slot whose engagement has no billing code at all must still
        # appear, flagged as uncoded, so missing codes are visible.
        monday = _monday(timezone.now())
        self._slot(monday, monday.replace(hour=17, minute=30))
        day = monday.date()
        alloc = build_user_code_allocation(
            self.user, day - timedelta(days=1), day + timedelta(days=1)
        )
        self.assertEqual(alloc["per_code"], {})
        self.assertIn(day, alloc["per_day"])
        entries = alloc["per_day"][day]
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]["code"])
        self.assertEqual(entries[0]["kind"], "phase")
        self.assertGreater(alloc["uncoded"]["hours"], 0)
        self.assertEqual(len(alloc["uncoded"]["by_target"]), 1)


class BuildCodeAnalyticsTests(TestCase):
    """The cross-user analytics roll-up: correctness and query batching."""

    def setUp(self):
        self.root = User.objects.create_user(email="root@an.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="AnUnit")
        self.client_obj = Client.objects.create(name="Acme")
        self.job = Job.objects.create(
            title="J", client=self.client_obj, unit=self.unit,
            created_by=self.root, account_manager=self.root,
        )
        self.phase = Phase.objects.create(
            job=self.job, title="P1", status=PhaseStatuses.SCHEDULED_CONFIRMED,
        )
        self.code = BillingCode.objects.create(
            code="A-1", client=self.client_obj, is_chargeable=True
        )
        BillingCodeAssignment.objects.create(code=self.code, job=self.job)
        self.delivery_type = TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.DELIVERY
        )
        # Three users each booked a single working day on the coded phase.
        self.monday = _monday(timezone.now())
        self.users = [
            User.objects.create_user(email=f"a{i}@an.com", password="pw")
            for i in range(3)
        ]
        for u in self.users:
            TimeSlot.objects.create(
                user=u, slot_type=self.delivery_type, phase=self.phase,
                start=self.monday, end=self.monday.replace(hour=17, minute=30),
                deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            )
        self.win = (self.monday.date() - timedelta(days=1),
                    self.monday.date() + timedelta(days=1))

    def test_matches_sum_of_per_user_allocations(self):
        from chaotica_utils.utils import build_code_analytics

        analytics = build_code_analytics(self.users, *self.win)
        per_user_hours = sum(
            build_user_code_allocation(u, *self.win)["per_code"][self.code.id]["hours"]
            for u in self.users
        )
        code_summary = analytics["per_code"][self.code.id]
        self.assertEqual(code_summary["hours"], per_user_hours)
        self.assertEqual(code_summary["days"], 3)  # one person-day each
        self.assertEqual(analytics["totals"]["hours"], per_user_hours)
        self.assertEqual(analytics["totals"]["chargeable"], per_user_hours)
        # by_client rolls the single client's code up.
        bucket = analytics["by_client"][self.client_obj.id]
        self.assertEqual(bucket["client"], self.client_obj)
        self.assertEqual(bucket["codes"], {self.code.id})

    def test_query_count_does_not_grow_with_cohort_size(self):
        """The roll-up must not fan out per user (the original perf bug).

        The same set of batched queries should serve one user or the whole
        cohort — the count is constant, not linear in the number of users.
        """
        from chaotica_utils.utils import build_code_analytics
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as one:
            build_code_analytics(self.users[:1], *self.win)
        with CaptureQueriesContext(connection) as many:
            build_code_analytics(self.users, *self.win)

        self.assertEqual(len(many), len(one))
        self.assertLessEqual(len(many), 6)

    def test_single_code_matches_cohort_rollup(self):
        from chaotica_utils.utils import build_code_analytics, build_single_code_analytics

        cohort = build_code_analytics(self.users, *self.win)["per_code"][self.code.id]
        one = build_single_code_analytics(self.code, self.users, *self.win)
        self.assertEqual(one["totals"]["hours"], cohort["hours"])
        self.assertEqual(one["totals"]["days"], cohort["days"])
        self.assertEqual(one["totals"]["people"], 3)
        self.assertEqual({r["user"] for r in one["by_user"]}, set(self.users))
        # All the time is on the one phase, and lands in its month.
        self.assertEqual(len(one["by_target"]), 1)
        self.assertEqual(one["by_target"][0]["hours"], cohort["hours"])
        self.assertEqual(sum(m["hours"] for m in one["by_month"]), cohort["hours"])

    def test_single_code_ignores_phase_override(self):
        """A phase with its own codes doesn't inherit the job's code."""
        from chaotica_utils.utils import build_single_code_analytics

        other = BillingCode.objects.create(code="B-2", client=self.client_obj)
        BillingCodeAssignment.objects.create(code=other, phase=self.phase)
        one = build_single_code_analytics(self.code, self.users, *self.win)
        self.assertEqual(one["totals"]["hours"], 0)
        self.assertEqual(one["by_user"], [])

    def test_unassigned_code_is_empty(self):
        from chaotica_utils.utils import build_single_code_analytics

        unused = BillingCode.objects.create(code="UNUSED")
        one = build_single_code_analytics(unused, self.users, *self.win)
        self.assertEqual(one["totals"], {"hours": 0, "days": 0, "people": 0})


class BillingCodeScopingTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser(email="root@test.com", password="pw")
        self.client_a = Client.objects.create(name="Acme")
        self.internal_code = BillingCode.objects.create(code="INT-1")
        self.client_code = BillingCode.objects.create(
            code="ACME-1", client=self.client_a
        )
        self.outsider = User.objects.create_user(
            email="out@test.com", password="pw"
        )

    def test_for_user_hides_unreachable_client_codes(self):
        reachable = BillingCode.objects.for_user(self.outsider)
        codes = set(reachable.values_list("code", flat=True))
        # Client-less/internal codes are always reachable; the client code is
        # not, because the outsider has no jobs in that client's unit.
        self.assertIn("INT-1", codes)
        self.assertNotIn("ACME-1", codes)

    def test_superuser_sees_everything(self):
        codes = set(
            BillingCode.objects.for_user(self.root).values_list("code", flat=True)
        )
        self.assertIn("ACME-1", codes)
        self.assertIn("INT-1", codes)


class BillingViewSmokeTests(TestCase):
    """Render the new pages to catch template/context errors, and assert the
    Code Allocations access gate (self + managers only)."""

    def setUp(self):
        self.root = User.objects.create_superuser(email="root@test.com", password="pw")
        self.owner = User.objects.create_user(email="owner@test.com", password="pw")
        self.manager = User.objects.create_user(email="mgr@test.com", password="pw")
        self.owner.manager = self.manager
        self.owner.save()
        self.stranger = User.objects.create_user(email="str@test.com", password="pw")
        self.http = TestHttpClient(HTTP_HOST="localhost")

    def test_own_allocation_ok(self):
        self.http.force_login(self.owner)
        resp = self.http.get(
            reverse("user_code_allocation", kwargs={"email": self.owner.email})
        )
        self.assertEqual(resp.status_code, 200)

    def test_manager_can_view_report_allocation(self):
        self.http.force_login(self.manager)
        resp = self.http.get(
            reverse("user_code_allocation", kwargs={"email": self.owner.email})
        )
        self.assertEqual(resp.status_code, 200)

    def test_stranger_forbidden(self):
        self.http.force_login(self.stranger)
        resp = self.http.get(
            reverse("user_code_allocation", kwargs={"email": self.owner.email})
        )
        self.assertEqual(resp.status_code, 403)

    def test_analytics_renders(self):
        self.http.force_login(self.root)  # superuser has view_billingcode
        url = reverse("billingcode_analytics")
        for qs in ("", "?start_date=2026-01-01&end_date=2026-03-31", "?dateRange=bad"):
            resp = self.http.get(url + qs)
            self.assertEqual(resp.status_code, 200, qs)

    def test_code_list_detail_and_analytics_tab_render(self):
        code = BillingCode.objects.create(code="INT-9", is_internal=True)
        self.http.force_login(self.root)
        self.assertEqual(self.http.get(reverse("billingcode_list")).status_code, 200)
        self.assertEqual(
            self.http.get(reverse("billingcode_detail", kwargs={"code": code.code})).status_code,
            200,
        )
        resp = self.http.get(
            reverse("billingcode_analytics_partial", kwargs={"code": code.code})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("stats-range-picker", json.loads(resp.content)["html"])

    def test_analytics_tab_hides_unreachable_code(self):
        client_code = BillingCode.objects.create(
            code="SECRET-1", client=Client.objects.create(name="Hidden")
        )
        self.http.force_login(self.stranger)
        resp = self.http.get(
            reverse("billingcode_analytics_partial", kwargs={"code": client_code.code})
        )
        self.assertIn(resp.status_code, (403, 404))

    def test_wbs_page_removed(self):
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("billingcode_wbs_list")


class BuildCohortCodeAllocationTests(TestCase):
    """Team / org-unit billing tab engine: per-member stats must equal the
    member's own Billing Codes page, with batched (constant) queries."""

    def setUp(self):
        from jobtracker.models import JobSupportTeamRole, SupportBudgetDraw

        self.root = User.objects.create_user(email="root@co.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="CoUnit")
        self.client_obj = Client.objects.create(name="Acme")
        self.delivery_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
        self.leave_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.LEAVE)

        def job(title):
            return Job.objects.create(
                title=title, client=self.client_obj, unit=self.unit,
                created_by=self.root, account_manager=self.root,
            )

        self.coded_job = job("Coded")
        self.uncoded_job = job("Uncoded")
        self.code_a = BillingCode.objects.create(code="A-1", client=self.client_obj, is_chargeable=True)
        self.code_b = BillingCode.objects.create(code="B-1", client=self.client_obj)
        BillingCodeAssignment.objects.create(code=self.code_a, job=self.coded_job)
        p_coded = Phase.objects.create(job=self.coded_job, title="P1", status=PhaseStatuses.IN_PROGRESS)
        p_uncoded = Phase.objects.create(job=self.uncoded_job, title="P2", status=PhaseStatuses.IN_PROGRESS)
        p_multi = Phase.objects.create(job=self.coded_job, title="P3", status=PhaseStatuses.IN_PROGRESS)
        BillingCodeAssignment.objects.create(code=self.code_a, phase=p_multi)
        BillingCodeAssignment.objects.create(code=self.code_b, phase=p_multi)

        self.monday = _monday(timezone.now())
        self.users = [
            User.objects.create_user(
                email=f"c{i}@co.com", password="pw", first_name=f"F{i}", last_name=f"L{i}"
            )
            for i in range(4)
        ]
        u0, u1, u2, u3 = self.users

        def slot(user, phase, day_offset, kind=None, end_hour=17):
            start = self.monday + timedelta(days=day_offset)
            return TimeSlot.objects.create(
                user=user, slot_type=kind or self.delivery_type, phase=phase,
                start=start, end=start.replace(hour=end_hour),
                deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            )

        # u0: coded day overlapped by half a day's leave (leave wins).
        slot(u0, p_coded, 0)
        slot(u0, None, 0, kind=self.leave_type, end_hour=13)
        slot(u0, p_coded, 1)
        # u1: uncoded work + a coded day.
        slot(u1, p_uncoded, 0)
        slot(u1, p_coded, 2)
        # u2: multi-code day + a support cash-out on the coded job.
        slot(u2, p_multi, 1)
        role = JobSupportTeamRole.objects.create(
            job=self.coded_job, user=u2, profile_percent=Decimal("100")
        )
        SupportBudgetDraw.objects.create(
            support_role=role, user=u2,
            period_start=self.monday.date(), period_end=self.monday.date() + timedelta(days=4),
            hours_drawn=Decimal("5"), lcr_at_draw=Decimal("50"), money_drawn=Decimal("250"),
        )
        # u3: nothing booked.
        self.win = (self.monday.date(), self.monday.date() + timedelta(days=6))

    def test_rows_equal_per_user_page(self):
        from chaotica_utils.utils import build_cohort_code_allocation

        cohort = build_cohort_code_allocation(self.users, *self.win)
        self.assertEqual([r["user"] for r in cohort["rows"]], self.users)  # by name
        for row in cohort["rows"]:
            fresh = User.objects.get(pk=row["user"].pk)
            expected = build_user_code_allocation(fresh, *self.win)["stats"]
            self.assertEqual(row["stats"], expected, row["user"])
        # The fixture really exercises leave-wins, uncoded and support.
        stats = {r["user"].email: r["stats"] for r in cohort["rows"]}
        self.assertGreater(stats["c0@co.com"]["unavailable_hours"], 0)
        self.assertGreater(stats["c1@co.com"]["uncoded_hours"], 0)
        self.assertEqual(stats["c2@co.com"]["support_hours"], Decimal("5"))
        self.assertEqual(stats["c3@co.com"]["coded_hours"], 0)
        # Totals and the code roll-up are the per-member sums.
        self.assertEqual(
            cohort["totals"]["coded_hours"],
            sum((r["stats"]["coded_hours"] for r in cohort["rows"]), Decimal(0)),
        )
        self.assertEqual(
            sum((c["hours"] for c in cohort["per_code"].values()), Decimal(0)),
            cohort["totals"]["coded_hours"] + cohort["totals"]["support_hours"],
        )
        self.assertIn(self.code_b.id, cohort["per_code"])

    def test_query_count_constant_in_cohort_size(self):
        from chaotica_utils.utils import build_cohort_code_allocation
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        u0, u1, u2, u3 = self.users
        with CaptureQueriesContext(connection) as two:
            build_cohort_code_allocation([u2, u0], *self.win)
        with CaptureQueriesContext(connection) as four:
            build_cohort_code_allocation([u2, u0, u1, u3], *self.win)
        self.assertEqual(len(four), len(two))


class CohortBillingTabViewTests(TestCase):
    """Team (owners) and org-unit (can_view_all_leave_requests) Billing tab
    partials."""

    def setUp(self):
        from guardian.shortcuts import assign_perm
        from jobtracker.models import Team, TeamMember

        self.root = User.objects.create_user(email="root@tab.com", password="pw")
        self.root.is_superuser = False
        self.root.save()
        self.unit = OrganisationalUnit.objects.create(name="TabUnit")
        self.team = Team.objects.create(name="Tab team", slug="tab-team")
        self.owner = User.objects.create_user(email="own@tab.com", password="pw")
        self.member = User.objects.create_user(
            email="mem@tab.com", password="pw", first_name="Mem", last_name="Ber"
        )
        self.stranger = User.objects.create_user(email="str@tab.com", password="pw")
        self.team.owners.add(self.owner)
        TeamMember.objects.create(
            team=self.team, user=self.member,
            joined_at=timezone.now().date() - timedelta(days=30),
        )
        for u in (self.owner, self.stranger):
            assign_perm("jobtracker.view_team", u)
            assign_perm("jobtracker.view_team", u, self.team)
        self.unit.members.create(member=self.member)
        self.viewer = User.objects.create_user(email="view@tab.com", password="pw")
        assign_perm("jobtracker.can_view_jobs", self.viewer, self.unit)
        assign_perm("jobtracker.view_organisationalunit", self.viewer, self.unit)
        assign_perm("jobtracker.can_view_all_leave_requests", self.viewer, self.unit)
        # A consultant: sees the unit's jobs but not colleagues' hours.
        self.consultant = User.objects.create_user(email="con@tab.com", password="pw")
        assign_perm("jobtracker.can_view_jobs", self.consultant, self.unit)
        assign_perm("jobtracker.view_organisationalunit", self.consultant, self.unit)
        self.http = TestHttpClient(HTTP_HOST="localhost")

    def _team_url(self):
        return reverse("team_billing_partial", kwargs={"slug": self.team.slug})

    def _unit_url(self):
        return reverse("orgunit_billing_partial", kwargs={"slug": self.unit.slug})

    def test_team_owner_sees_members(self):
        self.http.force_login(self.owner)
        resp = self.http.get(self._team_url() + "?start_date=2026-09-01&end_date=2026-09-14")
        self.assertEqual(resp.status_code, 200)
        html = resp.json()["html"]
        self.assertIn("Mem Ber", html)
        self.assertIn("Per code", html)
        self.assertIn("data-billing-range", html)
        # Owner isn't the member's manager -> no profile link.
        self.assertNotIn(
            reverse("user_code_allocation", kwargs={"email": self.member.email}), html
        )

    def test_team_non_owner_forbidden(self):
        self.http.force_login(self.stranger)
        self.assertEqual(self.http.get(self._team_url()).status_code, 403)

    def test_team_superuser_allowed_and_tab_rendered(self):
        su = User.objects.create_superuser(email="su@tab.com", password="pw")
        self.http.force_login(su)
        self.assertEqual(self.http.get(self._team_url()).status_code, 200)
        body = self.http.get(
            reverse("team_detail", kwargs={"slug": self.team.slug})
        ).content.decode()
        self.assertIn('id="billing-tab"', body)

    def test_unit_requires_leave_visibility(self):
        detail = reverse("organisationalunit_detail", kwargs={"slug": self.unit.slug})
        self.http.force_login(self.stranger)
        self.assertEqual(self.http.get(self._unit_url()).status_code, 403)
        self.http.force_login(self.consultant)
        self.assertEqual(self.http.get(self._unit_url()).status_code, 403)
        self.assertNotContains(self.http.get(detail), 'id="billing-tab"')
        self.http.force_login(self.viewer)
        resp = self.http.get(self._unit_url())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Mem Ber", resp.json()["html"])
        self.assertContains(self.http.get(detail), 'id="billing-tab"')

    def test_role_mapping_gives_tab_to_service_delivery_and_manager_only(self):
        from chaotica_utils.enums import UnitRoles

        perm = "jobtracker.can_view_all_leave_requests"
        holders = {role for role, perms in UnitRoles.PERMISSIONS if perm in perms}
        self.assertEqual(holders, {UnitRoles.SERVICE_DELIVERY, UnitRoles.MANAGER})

    def test_profile_link_only_for_manageable_members(self):
        self.member.manager = self.viewer
        self.member.save()
        self.http.force_login(self.viewer)
        html = self.http.get(self._unit_url()).json()["html"]
        self.assertIn(
            reverse("user_code_allocation", kwargs={"email": self.member.email}), html
        )
