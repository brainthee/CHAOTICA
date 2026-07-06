from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext

from django.core.cache import cache
from django.test import SimpleTestCase

from chaotica_utils.models import User
from jobtracker.models.skill import SkillCategory, Skill, UserSkill
from jobtracker.models.service import Service
from jobtracker.models.timeslot import TimeSlot, TimeSlotType
from jobtracker.enums import UserSkillRatings
from jobtracker import scheduling_assistant as sa


class RankCandidatesForServiceTests(TestCase):
    def setUp(self):
        # get_service_readiness_breakdown is cached by service id + skill counts;
        # LocMemCache is not rolled back between tests, so clear it to avoid stale
        # breakdowns leaking across tests.
        cache.clear()
        self.category = SkillCategory.objects.create(name="Testing")
        self.skill_a = Skill.objects.create(name="Skill A", category=self.category)
        self.skill_b = Skill.objects.create(name="Skill B", category=self.category)

        self.service = Service.objects.create(name="Widget Assessment")
        self.service.skillsRequired.add(self.skill_a, self.skill_b)

        # A user at each competency tier (all required skills) + a partial user.
        self.specialist = User.objects.create_user(email="spec@example.com", password="x")
        self.independent = User.objects.create_user(email="indep@example.com", password="x")
        self.support = User.objects.create_user(email="supp@example.com", password="x")
        self.partial = User.objects.create_user(email="part@example.com", password="x")

        def rate(user, rating, skills):
            for sk in skills:
                UserSkill.objects.create(user=user, skill=sk, rating=rating)

        rate(self.specialist, UserSkillRatings.SPECIALIST, [self.skill_a, self.skill_b])
        rate(self.independent, UserSkillRatings.CAN_DO_ALONE, [self.skill_a, self.skill_b])
        rate(self.support, UserSkillRatings.CAN_DO_WITH_SUPPORT, [self.skill_a, self.skill_b])
        # Partial: only one of the two required skills -> tier 0 -> must be excluded.
        rate(self.partial, UserSkillRatings.SPECIALIST, [self.skill_a])

        self.pool = User.objects.filter(
            pk__in=[self.specialist.pk, self.independent.pk, self.support.pk, self.partial.pk]
        )
        self.start = timezone.now().date()

    def _rank(self, weights=None, required=3):
        return sa.rank_candidates_for_service(
            service=self.service,
            required_working_days=required,
            search_start=self.start,
            search_end=self.start + timedelta(days=30),
            candidate_pool=self.pool,
            weights=weights,
        )

    def test_excludes_users_missing_required_skills(self):
        ids = {c.user.pk for c in self._rank()}
        self.assertIn(self.specialist.pk, ids)
        self.assertIn(self.independent.pk, ids)
        self.assertIn(self.support.pk, ids)
        self.assertNotIn(self.partial.pk, ids)

    def test_tier_ordering_by_skill(self):
        # All else equal, higher competency should rank higher.
        cands = self._rank()
        by_user = {c.user.pk: c for c in cands}
        self.assertEqual(by_user[self.specialist.pk].tier, 3)
        self.assertEqual(by_user[self.independent.pk].tier, 2)
        self.assertEqual(by_user[self.support.pk].tier, 1)
        self.assertGreater(
            by_user[self.specialist.pk].score, by_user[self.support.pk].score
        )
        # First result is the specialist.
        self.assertEqual(cands[0].user.pk, self.specialist.pk)

    def test_earliest_window_when_free(self):
        cand = next(c for c in self._rank() if c.user.pk == self.specialist.pk)
        self.assertIsNotNone(cand.earliest_start)
        self.assertTrue(cand.has_window)
        # 3 working days requested -> end is on/after start.
        self.assertGreaterEqual(cand.earliest_end, cand.earliest_start)

    def test_no_window_when_fully_occupied(self):
        # Block every day in the search window for the specialist.
        st = TimeSlotType.objects.create(
            name="Busy", is_working=True, is_delivery=False, is_assignable=False
        )
        TimeSlot.objects.create(
            user=self.specialist,
            slot_type=st,
            start=timezone.make_aware(
                timezone.datetime.combine(self.start, timezone.datetime.min.time())
            ),
            end=timezone.make_aware(
                timezone.datetime.combine(
                    self.start + timedelta(days=40), timezone.datetime.max.time()
                )
            ),
        )
        cand = next(c for c in self._rank() if c.user.pk == self.specialist.pk)
        self.assertIsNone(cand.earliest_start)
        self.assertFalse(cand.has_window)
        self.assertEqual(cand.signals["availability_window"].raw, 0.0)

    def test_weight_toggle_drops_signal(self):
        # Turn history + seniority off (weight 0): they must not appear in signals.
        cands = self._rank(weights={"history": 0, "seniority": 0})
        for c in cands:
            self.assertNotIn("history", c.signals)
            self.assertNotIn("seniority", c.signals)
            # skill + availability_window are always on.
            self.assertIn("skill", c.signals)
            self.assertIn("availability_window", c.signals)

    def test_query_count_does_not_scale_with_pool(self):
        # Guard against N+1: adding more candidates must NOT increase the query
        # count (all per-user data is bulk-loaded).
        cache.clear()
        with CaptureQueriesContext(connection) as small:
            self._rank()
        small_count = len(small.captured_queries)

        # Add several more capable users to the pool.
        extra_ids = [self.specialist.pk, self.independent.pk, self.support.pk, self.partial.pk]
        for i in range(6):
            u = User.objects.create_user(email=f"extra{i}@example.com", password="x")
            UserSkill.objects.create(user=u, skill=self.skill_a, rating=UserSkillRatings.CAN_DO_ALONE)
            UserSkill.objects.create(user=u, skill=self.skill_b, rating=UserSkillRatings.CAN_DO_ALONE)
            extra_ids.append(u.pk)
        big_pool = User.objects.filter(pk__in=extra_ids)

        cache.clear()
        with CaptureQueriesContext(connection) as big:
            sa.rank_candidates_for_service(
                service=self.service,
                required_working_days=3,
                search_start=self.start,
                search_end=self.start + timedelta(days=30),
                candidate_pool=big_pool,
            )
        big_count = len(big.captured_queries)

        # Allow a tiny delta for query planner variance, but it must be flat.
        self.assertLessEqual(big_count, small_count + 2)

    def test_pinned_on_phase_sorts_first_regardless_of_score(self):
        # The support-tier user scores lowest, but pinning them (already on the
        # phase) must float them to the top and flag on_phase.
        cands = sa.rank_candidates_for_service(
            service=self.service,
            required_working_days=3,
            search_start=self.start,
            search_end=self.start + timedelta(days=30),
            candidate_pool=self.pool,
            pinned_ids={self.support.pk},
        )
        self.assertEqual(cands[0].user.pk, self.support.pk)
        self.assertTrue(cands[0].on_phase)
        self.assertFalse(any(c.on_phase for c in cands[1:]))

    def test_role_map_attaches_phase_roles(self):
        cands = sa.rank_candidates_for_service(
            service=self.service,
            required_working_days=3,
            search_start=self.start,
            candidate_pool=self.pool,
            pinned_ids={self.specialist.pk},
            role_map={self.specialist.pk: ["Lead", "Author"]},
        )
        top = cands[0]
        self.assertEqual(top.user.pk, self.specialist.pk)
        self.assertEqual(top.phase_roles, ["Lead", "Author"])

    def test_pinned_user_outside_pool_is_included(self):
        # Someone already on the phase but NOT in the candidate pool is still shown.
        outsider = User.objects.create_user(email="outsider@example.com", password="x")
        cands = sa.rank_candidates_for_service(
            service=self.service,
            required_working_days=3,
            search_start=self.start,
            candidate_pool=self.pool,  # outsider is not in here
            pinned_ids={outsider.pk},
        )
        ids = {c.user.pk for c in cands}
        self.assertIn(outsider.pk, ids)
        self.assertEqual(cands[0].user.pk, outsider.pk)

    def test_empty_pool_returns_empty(self):
        cands = sa.rank_candidates_for_service(
            service=self.service,
            required_working_days=3,
            search_start=self.start,
            candidate_pool=User.objects.none(),
        )
        self.assertEqual(cands, [])


class ServiceCompetencyTests(TestCase):
    """Regression tests for Service competency helpers — the support tier used to
    return nobody due to a Count-over-joined-M2M bug."""

    def setUp(self):
        cache.clear()
        self.cat = SkillCategory.objects.create(name="Comp")
        self.a = Skill.objects.create(name="CA", category=self.cat)
        self.b = Skill.objects.create(name="CB", category=self.cat)
        self.service = Service.objects.create(name="Comp Service")
        self.service.skillsRequired.add(self.a, self.b)

        def mk(email, ra, rb):
            u = User.objects.create_user(email=email, password="x")
            UserSkill.objects.create(user=u, skill=self.a, rating=ra)
            UserSkill.objects.create(user=u, skill=self.b, rating=rb)
            return u

        R = UserSkillRatings
        self.spec = mk("c_spec@x.com", R.SPECIALIST, R.SPECIALIST)
        self.alone = mk("c_alone@x.com", R.CAN_DO_ALONE, R.CAN_DO_ALONE)
        self.support = mk("c_supp@x.com", R.CAN_DO_WITH_SUPPORT, R.CAN_DO_WITH_SUPPORT)
        self.support_mixed = mk("c_supmix@x.com", R.SPECIALIST, R.CAN_DO_WITH_SUPPORT)
        # Only one of the two required skills -> partial.
        self.partial = User.objects.create_user(email="c_part@x.com", password="x")
        UserSkill.objects.create(user=self.partial, skill=self.a, rating=R.SPECIALIST)

    def _emails(self, qs):
        return set(qs.values_list("email", flat=True))

    def test_specialist_needs_all_required_at_specialist(self):
        self.assertEqual(self._emails(self.service.get_users_specialist()), {"c_spec@x.com"})

    def test_can_do_alone_includes_specialists(self):
        self.assertEqual(
            self._emails(self.service.get_users_can_do_alone()),
            {"c_spec@x.com", "c_alone@x.com"},
        )

    def test_can_do_with_support_is_not_empty(self):
        # The core regression: support-tier users must be returned.
        self.assertEqual(
            self._emails(self.service.get_users_can_do_with_support()),
            {"c_supp@x.com", "c_supmix@x.com"},
        )

    def test_missing_skills(self):
        self.assertEqual(self._emails(self.service.get_users_missing_skills()), {"c_part@x.com"})

    def test_readiness_breakdown_partitions_capable_users(self):
        bd = self.service.get_service_readiness_breakdown()
        self.assertEqual(self._emails(bd["specialists"]), {"c_spec@x.com"})
        self.assertEqual(self._emails(bd["independent_only"]), {"c_alone@x.com"})
        self.assertEqual(self._emails(bd["support_only"]), {"c_supp@x.com", "c_supmix@x.com"})
        self.assertEqual(bd["total_capable"], 4)


class AllocateManDaysTests(SimpleTestCase):
    def test_even_split_sums_to_total(self):
        self.assertEqual(sa.allocate_man_days(12, 3), [4, 4, 4])
        self.assertEqual(sum(sa.allocate_man_days(12, 3)), 12)

    def test_uneven_split_gives_extras_first(self):
        self.assertEqual(sa.allocate_man_days(13, 3), [5, 4, 4])
        self.assertEqual(sum(sa.allocate_man_days(13, 3)), 13)

    def test_more_people_than_days(self):
        self.assertEqual(sa.allocate_man_days(2, 3), [1, 1, 0])
        self.assertEqual(sum(sa.allocate_man_days(2, 3)), 2)


class BuildSplitPlanTests(SimpleTestCase):
    """Pure-function tests for the split-team planner layout. The key invariant:
    per-person day allocations must SUM to the scoped man-days (no over-utilisation)."""

    START = date(2026, 7, 6)  # a Monday

    def _by_user(self, plan):
        return {r["user_id"]: r for r in plan}

    def test_man_days_sum_to_scope_sequential(self):
        plan = sa.build_split_plan(
            user_ids=[1, 2, 3], coverage="sequential", total_days=12, start_date=self.START
        )
        self.assertEqual(sum(r["days"] for r in plan), 12)  # NOT 12 + segments
        rows = self._by_user(plan)
        self.assertEqual(rows[1]["role"], "lead")
        self.assertEqual(rows[3]["role"], "author")
        # Even split, laid back-to-back from day one.
        self.assertEqual([r["days"] for r in plan], [4, 4, 4])
        self.assertEqual(rows[1]["start"], self.START)
        self.assertLess(rows[1]["start"], rows[3]["start"])  # author last

    def test_man_days_sum_to_scope_parallel(self):
        plan = sa.build_split_plan(
            user_ids=[1, 2, 3], coverage="parallel", total_days=12, start_date=self.START
        )
        self.assertEqual(sum(r["days"] for r in plan), 12)
        rows = self._by_user(plan)
        # Everyone works concurrently from the same start (lead present throughout).
        self.assertTrue(all(r["start"] == self.START for r in plan))
        self.assertEqual(rows[1]["days"], 4)

    def test_lead_and_author_same_person(self):
        plan = sa.build_split_plan(
            user_ids=[1, 2], coverage="sequential", total_days=6,
            start_date=self.START, lead_id=1, author_id=1,
        )
        rows = self._by_user(plan)
        self.assertEqual(rows[1]["role"], "lead_author")
        self.assertEqual(rows[2]["role"], "tester")
        self.assertEqual(sum(r["days"] for r in plan), 6)

    def test_custom_lead_and_author(self):
        plan = sa.build_split_plan(
            user_ids=[1, 2, 3], coverage="sequential", total_days=9,
            start_date=self.START, lead_id=2, author_id=1,
        )
        rows = self._by_user(plan)
        self.assertEqual(rows[2]["role"], "lead")
        self.assertEqual(rows[1]["role"], "author")

    def test_single_person_is_lead_author(self):
        plan = sa.build_split_plan(
            user_ids=[1], coverage="sequential", total_days=8, start_date=self.START
        )
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["role"], "lead_author")
        self.assertEqual(plan[0]["days"], 8)


class PhaseDeliveryDayStatsTests(SimpleTestCase):
    """phase_delivery_day_stats derives scoped/scheduled/remaining without a DB."""

    class _StubPhase:
        def __init__(self, scoped, scheduled):
            self._scoped, self._scheduled = scoped, scheduled

        def get_total_scoped_days_by_type(self, role):
            return self._scoped

        def get_total_scheduled_days_by_type(self, role):
            return self._scheduled

    def test_remaining_when_under_scope(self):
        st = sa.phase_delivery_day_stats(self._StubPhase(32, 10))
        self.assertEqual(st["scoped"], 32)
        self.assertEqual(st["scheduled"], 10)
        self.assertEqual(st["remaining"], 22)
        self.assertFalse(st["over"])
        self.assertEqual(st["over_by"], 0)

    def test_over_scope_flagged(self):
        st = sa.phase_delivery_day_stats(self._StubPhase(10, 14))
        self.assertEqual(st["remaining"], -4)
        self.assertTrue(st["over"])
        self.assertEqual(st["over_by"], 4)
