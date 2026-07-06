"""Scheduling Assistant — rank people to deliver a phase/service.

Pure logic (no HTTP) so it is independently testable. Given a service (its
required/desired skills + qualifications), a required number of working days and
a search window, it produces a ranked list of candidates scored transparently on:

  * skill competency tier for the service  (Service.get_service_readiness_breakdown)
  * earliest available run of N working days (mirrors views.scheduler.working_day_runs,
    but bulk-computes holidays once by country to avoid a per-user query)
  * availability % over the window          (User.objects.calculate_bulk_utilization)
  * client onboarding status                (ClientOnboarding.status)
  * required/desired qualifications held     (QualificationRecord, AWARDED)
  * service delivery history                 (TimeSlot -> phase -> service)
  * seniority                                (current UserJobLevel.order)

Each signal keeps its raw 0..1 value, weight and a human label so the UI can show
*why* someone was suggested. Signals are individually toggleable via ``weights``:
a signal with weight 0 is dropped from the score (skill and availability always on).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.utils import timezone


DEFAULT_HORIZON_DAYS = 90
DEFAULT_JOB_DEFAULT_DAYS = 5  # fallback length for the job/indicative-services case
_HISTORY_CAP = 5  # history_count at/above which the history sub-score is maxed

# Weights sum to 1.0; a weight of 0 turns the signal off. skill + availability_window
# are always kept on (see _active_weights).
DEFAULT_WEIGHTS = {
    "availability_window": 0.35,
    "skill": 0.25,
    "onboarding": 0.12,
    "history": 0.12,
    "availability_pct": 0.08,
    "qualifications": 0.05,
    "seniority": 0.03,
}
ALWAYS_ON = ("skill", "availability_window")

_TIER_LABELS = {3: "Specialist", 2: "Can Do Alone", 1: "With Support", 0: "No skill requirement"}


@dataclass
class CandidateSignal:
    raw: float  # normalised 0..1
    weight: float
    label: str  # short human string for the "why" breakdown
    detail: dict = field(default_factory=dict)

    @property
    def contribution(self):
        """Points this signal contributes to the (un-normalised) score."""
        return round(self.raw * self.weight * 100, 1)


@dataclass
class Candidate:
    user: object
    tier: int | None
    tier_label: str
    earliest_start: date | None
    earliest_end: date | None
    run_length: int
    availability_pct: float
    utilisation_pct: float
    onboarding_status: str
    matched_quals: list = field(default_factory=list)
    missing_quals: list = field(default_factory=list)
    history_count: int = 0
    seniority_order: int = 999
    seniority_label: str = "No Level"
    on_phase: bool = False  # already booked on / assigned to this phase
    phase_roles: list = field(default_factory=list)  # e.g. ["Lead", "Author"]
    signals: dict = field(default_factory=dict)
    score: float = 0.0

    @property
    def has_window(self):
        return self.earliest_start is not None

    @property
    def missing_required_quals(self):
        return bool(self.missing_quals)


def _active_weights(weights):
    """Merge caller weights over defaults; force skill + availability on."""
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    for key in ALWAYS_ON:
        if not w.get(key):
            w[key] = DEFAULT_WEIGHTS[key]
    return {k: v for k, v in w.items() if v and v > 0}


def _aware(d, end=False):
    """date -> tz-aware datetime at start/end of day."""
    t = datetime.max.time() if end else datetime.min.time()
    return timezone.make_aware(datetime.combine(d, t))


def _expand_days(start_dt, end_dt):
    """Yield each date in [start_dt.date(), end_dt.date()] inclusive."""
    cur = start_dt.date()
    last = end_dt.date()
    while cur <= last:
        yield cur
        cur += timedelta(days=1)


def _find_window(business_days, holidays, occupied, search_start, search_end, required):
    """First run of ``required`` bookable working days in [search_start, search_end].

    A day is bookable if it is an org business day, not a holiday and not occupied.
    Non-working days don't break or count toward a run (a booking may span a
    weekend). Returns (start_date, end_date, run_len_working_days). If no run is
    long enough returns (None, None, longest_run_seen)."""
    run = []  # working-day dates in the current unbroken run
    best_len = 0
    cur, last = search_start, search_end
    while cur <= last:
        is_business = (cur.weekday() + 1) in business_days and cur not in holidays
        if is_business:
            if cur in occupied:
                best_len = max(best_len, len(run))
                run = []
            else:
                run.append(cur)
                if len(run) >= required:
                    return run[0], run[-1], len(run)
        cur += timedelta(days=1)
    best_len = max(best_len, len(run))
    return None, None, best_len


def rank_candidates_for_service(
    *,
    service,
    required_working_days,
    search_start,
    search_end=None,
    client=None,
    unit=None,
    candidate_pool=None,
    weights=None,
    pinned_ids=None,
    role_map=None,
):
    """Rank candidates able to deliver ``service``.

    Args:
        service: a Service instance.
        required_working_days: consecutive working days needed (>=1).
        search_start / search_end: date window to search availability in.
        client: Client for onboarding scoring (optional).
        unit: OrganisationalUnit used as fallback pool when candidate_pool is None.
        candidate_pool: pre-filtered, permission-scoped User queryset (from
            jobtracker.utils._filter_users_on_query). Strongly preferred.
        weights: overrides for DEFAULT_WEIGHTS (0 = signal off).
        pinned_ids: user ids already on the phase — always included (even if they
            don't meet the skill/pool filters) and sorted to the top, flagged
            ``on_phase`` so the UI can highlight them.

    Returns a list[Candidate] sorted best-first (pinned/on-phase first).
    """
    from chaotica_utils.models import User, Holiday
    from chaotica_utils.models.job_levels import JobLevel, UserJobLevel
    from .models import TimeSlot, ClientOnboarding
    from .enums import QualificationStatus

    required_working_days = max(1, int(required_working_days or 1))
    if search_end is None:
        search_end = search_start + timedelta(days=DEFAULT_HORIZON_DAYS)
    horizon_days = max(1, (search_end - search_start).days)
    active_weights = _active_weights(weights)
    pinned_ids = {int(u) for u in pinned_ids} if pinned_ids else set()
    role_map = role_map or {}

    # --- 1. Skill tiers from a single readiness call ---------------------------
    required_skill_count = service.skillsRequired.count()
    pool_ids = None
    if candidate_pool is not None:
        pool_ids = set(candidate_pool.values_list("id", flat=True))

    # Tier = competency for the WHOLE service: a user must hold ALL required
    # skills, and their tier is the *weakest* of those ratings (specialist only
    # if every required skill is specialist). Computed directly from UserSkill in
    # one query (avoids the buggy/cached readiness helper).
    tier_by_id = None
    if required_skill_count:
        from collections import defaultdict
        from .models.skill import UserSkill
        from .enums import UserSkillRatings

        required_skill_ids = set(service.skillsRequired.values_list("id", flat=True))
        skill_q = UserSkill.objects.filter(
            skill_id__in=required_skill_ids, user__is_active=True
        )
        if pool_ids is not None:
            # Keep pinned (on-phase) people in scope even if outside the pool.
            skill_q = skill_q.filter(user_id__in=(pool_ids | pinned_ids))

        ratings_by_user = defaultdict(dict)
        for uid, sid, rating in skill_q.values_list("user_id", "skill_id", "rating"):
            # Keep the highest rating recorded for a skill (defensive; unique_together
            # should make one row per (user, skill)).
            if rating > ratings_by_user[uid].get(sid, -1):
                ratings_by_user[uid][sid] = rating

        tier_by_id = {}
        for uid, sk in ratings_by_user.items():
            if not required_skill_ids.issubset(sk.keys()):
                continue  # missing at least one required skill -> can't deliver
            min_rating = min(sk[s] for s in required_skill_ids)
            if min_rating >= UserSkillRatings.SPECIALIST:
                tier_by_id[uid] = 3
            elif min_rating >= UserSkillRatings.CAN_DO_ALONE:
                tier_by_id[uid] = 2
            elif min_rating >= UserSkillRatings.CAN_DO_WITH_SUPPORT:
                tier_by_id[uid] = 1
            # NO_EXPERIENCE in a required skill -> excluded

    # --- 2. Candidate id set (intersect tiers with the permission-scoped pool) --
    if tier_by_id is not None:
        cand_ids = set(tier_by_id.keys())
        if pool_ids is not None:
            cand_ids &= pool_ids
    else:
        # Service defines no required skills -> no competency constraint.
        if pool_ids is not None:
            cand_ids = set(pool_ids)
        elif unit is not None:
            cand_ids = set(
                unit.get_activeMembers().values_list("pk", flat=True)
                if hasattr(unit, "get_activeMembers")
                else unit.members.filter(
                    left_date__isnull=True, member__is_active=True
                ).values_list("member_id", flat=True)
            )
        else:
            cand_ids = set()

    # Always surface people already on the phase, even if they'd otherwise be
    # filtered out (wrong unit, missing a skill, etc.).
    cand_ids |= pinned_ids

    if not cand_ids:
        return []

    pool_qs = (
        User.objects.filter(pk__in=cand_ids)
        .prefetch_related(
            "unit_memberships__unit",
            "job_level_history__job_level",
        )
    )

    # --- 3. Bulk loads (one query each, avoid N+1) -----------------------------
    start_dt, end_dt = _aware(search_start), _aware(search_end, end=True)

    # Occupied working days per user (any slot blocks a run, like the booking
    # "around" mode). One query for everyone.
    occupied_by_user = {uid: set() for uid in cand_ids}
    for uid, s, e in TimeSlot.objects.filter(
        user_id__in=cand_ids, end__gte=start_dt, start__lte=end_dt
    ).values_list("user_id", "start", "end"):
        occupied_by_user[uid].update(_expand_days(s, e))

    # Availability / utilisation over the window. One aggregate pass.
    util = User.objects.calculate_bulk_utilization(pool_qs, start_dt, end_dt)
    by_user = util.get("by_user", {})

    # Client onboarding. One query.
    onboarding_by_user = {}
    client_needs_onboarding = bool(client and getattr(client, "onboarding_required", False))
    if client:
        for ob in ClientOnboarding.objects.filter(client=client, user_id__in=cand_ids):
            onboarding_by_user[ob.user_id] = ob.status()

    # Service delivery history. One aggregate query.
    from django.db.models import Count

    history_by_user = {}
    for row in (
        TimeSlot.objects.filter(user_id__in=cand_ids, phase__service=service)
        .values("user_id")
        .annotate(n=Count("phase", distinct=True))
    ):
        history_by_user[row["user_id"]] = row["n"]

    # Qualifications. One query, matched against the service's required/desired.
    required_qual_ids = set(service.qualificationsRequired.values_list("id", flat=True))
    desired_qual_ids = set(service.qualificationsDesired.values_list("id", flat=True))
    relevant_qual_ids = required_qual_ids | desired_qual_ids
    held_quals_by_user = {uid: {} for uid in cand_ids}
    if relevant_qual_ids:
        from .models import QualificationRecord

        for rec in QualificationRecord.objects.filter(
            user_id__in=cand_ids,
            status=QualificationStatus.AWARDED,
            qualification_id__in=relevant_qual_ids,
        ).select_related("qualification"):
            held_quals_by_user.setdefault(rec.user_id, {})[rec.qualification_id] = rec.qualification

    # Current job level per user. One query (get_current_level is per-call, so we
    # bulk-load here to avoid an N+1 over the candidate pool).
    level_by_user = {}
    for lvl in (
        UserJobLevel.objects.filter(user_id__in=cand_ids, is_current=True)
        .select_related("job_level")
    ):
        level_by_user[lvl.user_id] = lvl

    # Seniority range for normalisation.
    max_order = (
        JobLevel.objects.filter(is_active=True).order_by("-order").values_list("order", flat=True).first()
        or 1
    )

    # Required qualifications, evaluated once (used per candidate for the
    # missing-quals list).
    required_quals = list(service.qualificationsRequired.all())

    # Bulk holiday fetch by country (avoids a per-user holiday query).
    countries = {u.country for u in pool_qs}
    from django.db.models import Q as _Q

    holidays_by_country = {}
    global_holidays = set()
    for country, hdate in Holiday.objects.filter(
        _Q(country__in=[c for c in countries if c]) | _Q(country__isnull=True),
        date__gte=search_start,
        date__lte=search_end,
    ).values_list("country", "date"):
        if country is None:
            global_holidays.add(hdate)
        else:
            holidays_by_country.setdefault(country, set()).add(hdate)

    # --- 4. Build candidates ----------------------------------------------------
    candidates = []
    for user in pool_qs:
        uid = user.pk
        tier = tier_by_id.get(uid) if tier_by_id is not None else 0

        membership = user.unit_memberships.first()
        business_days = (
            membership.unit.businessHours_days
            if membership and membership.unit.businessHours_days
            else [1, 2, 3, 4, 5]
        )
        holidays = set(holidays_by_country.get(user.country, set())) | global_holidays

        w_start, w_end, run_len = _find_window(
            business_days,
            holidays,
            occupied_by_user.get(uid, set()),
            search_start,
            search_end,
            required_working_days,
        )

        stat = by_user.get(uid, {})
        avail_pct = stat.get("available_percentage") or 0
        util_pct = stat.get("utilisation_percentage") or 0

        onboarding_status = onboarding_by_user.get(uid)
        if onboarding_status is None:
            onboarding_status = "pending" if client_needs_onboarding else "n_a"

        held = held_quals_by_user.get(uid, {})
        matched_required = [held[q] for q in required_qual_ids if q in held]
        missing_required = [q for q in required_qual_ids if q not in held]
        matched_desired = [held[q] for q in desired_qual_ids if q in held]

        history_count = history_by_user.get(uid, 0)

        current_level = level_by_user.get(uid)
        seniority_order = current_level.job_level.order if current_level else 999
        seniority_label = str(current_level.job_level) if current_level else "No Level"

        c = Candidate(
            user=user,
            tier=tier,
            tier_label=_TIER_LABELS.get(tier, "Unknown"),
            earliest_start=w_start,
            earliest_end=w_end,
            run_length=run_len,
            availability_pct=round(avail_pct, 1),
            utilisation_pct=round(util_pct, 1),
            onboarding_status=onboarding_status,
            matched_quals=matched_required + matched_desired,
            missing_quals=[q for q in required_quals if q.id in missing_required],
            history_count=history_count,
            seniority_order=seniority_order,
            seniority_label=seniority_label,
            on_phase=uid in pinned_ids,
            phase_roles=role_map.get(uid, []),
        )
        _score_candidate(
            c,
            active_weights=active_weights,
            tier_by_id=tier_by_id,
            search_start=search_start,
            horizon_days=horizon_days,
            required_qual_ids=required_qual_ids,
            desired_qual_ids=desired_qual_ids,
            matched_required=matched_required,
            matched_desired=matched_desired,
            max_order=max_order,
        )
        candidates.append(c)

    # People already on the phase float to the top (regardless of score), then
    # everyone else by score.
    candidates.sort(
        key=lambda c: (
            not c.on_phase,
            -c.score,
            (c.earliest_start or date.max),
            c.seniority_order,
        )
    )
    return candidates


def _score_candidate(
    c,
    *,
    active_weights,
    tier_by_id,
    search_start,
    horizon_days,
    required_qual_ids,
    desired_qual_ids,
    matched_required,
    matched_desired,
    max_order,
):
    signals = {}

    # skill
    if tier_by_id is None:
        skill_raw = 0.5  # no competency constraint -> neutral
    else:
        skill_raw = (c.tier or 0) / 3.0
    signals["skill"] = CandidateSignal(skill_raw, active_weights.get("skill", 0), c.tier_label)

    # availability_window
    if c.earliest_start is None:
        aw_raw = 0.0
        aw_label = "No free run in window"
    else:
        days_until = max(0, (c.earliest_start - search_start).days)
        aw_raw = max(0.0, 1.0 - days_until / horizon_days)
        aw_label = f"Free from {c.earliest_start:%a %d %b}"
    signals["availability_window"] = CandidateSignal(
        aw_raw, active_weights.get("availability_window", 0), aw_label
    )

    # availability_pct
    signals["availability_pct"] = CandidateSignal(
        min(1.0, (c.availability_pct or 0) / 100.0),
        active_weights.get("availability_pct", 0),
        f"{c.availability_pct:.0f}% available",
    )

    # onboarding
    ob_map = {"active": 1.0, "stale": 0.6, "pending": 0.3, "unknown": 0.3, "offboarded": 0.0, "n_a": 1.0}
    signals["onboarding"] = CandidateSignal(
        ob_map.get(c.onboarding_status, 0.3),
        active_weights.get("onboarding", 0),
        {"active": "Onboarded", "stale": "Onboarding stale", "pending": "Not onboarded",
         "offboarded": "Offboarded", "n_a": "No onboarding needed", "unknown": "Onboarding unknown"}.get(
            c.onboarding_status, "Onboarding unknown"
        ),
    )

    # qualifications
    if not required_qual_ids and not desired_qual_ids:
        q_raw = 1.0  # no qualification constraint -> neutral
        q_label = "No quals required"
    else:
        req_component = (
            len(matched_required) / len(required_qual_ids) if required_qual_ids else 1.0
        )
        des_bonus = (
            0.2 * (len(matched_desired) / len(desired_qual_ids)) if desired_qual_ids else 0.0
        )
        q_raw = min(1.0, req_component * (1.0 if not desired_qual_ids else 0.9) + des_bonus)
        if c.missing_required_quals:
            q_label = f"Missing {len(c.missing_quals)} required qual(s)"
        else:
            q_label = f"{len(c.matched_quals)} matching qual(s)"
    signals["qualifications"] = CandidateSignal(q_raw, active_weights.get("qualifications", 0), q_label)

    # history
    signals["history"] = CandidateSignal(
        min(1.0, c.history_count / _HISTORY_CAP),
        active_weights.get("history", 0),
        f"Delivered ×{c.history_count}" if c.history_count else "No prior delivery",
    )

    # seniority (higher = more senior; low weight, mainly a tie-break)
    sen_raw = max(0.0, 1.0 - (c.seniority_order / max_order)) if c.seniority_order < 999 else 0.0
    signals["seniority"] = CandidateSignal(
        sen_raw, active_weights.get("seniority", 0), c.seniority_label
    )

    # Weighted, normalised by the sum of active weights so toggling signals off
    # keeps scores on a comparable 0..100 scale.
    total_w = sum(active_weights.values()) or 1.0
    total = sum(
        sig.raw * sig.weight for name, sig in signals.items() if name in active_weights
    )
    c.score = round(100 * total / total_w, 1)
    # Only keep the signals that actually count toward the score for the UI.
    c.signals = {name: sig for name, sig in signals.items() if name in active_weights}


# --------------------------------------------------------------------------- #
# Adapters                                                                     #
# --------------------------------------------------------------------------- #

def phase_required_working_days(phase):
    """Working days needed for a phase's delivery, from scoped delivery hours."""
    hours = phase.delivery_hours or 0
    hid = phase.get_hours_in_day() or 0
    if not hid:
        return 1
    return max(1, math.ceil(float(hours) / float(hid))) if hours else 1


def phase_delivery_day_stats(phase):
    """Delivery-day utilisation for a phase: scoped vs already-scheduled vs
    remaining. Lets the assistant work with what's left rather than the whole
    scope. Values are working-days (floats, 1dp)."""
    from .enums import TimeSlotDeliveryRole

    scoped = float(phase.get_total_scoped_days_by_type(TimeSlotDeliveryRole.DELIVERY) or 0)
    scheduled = float(phase.get_total_scheduled_days_by_type(TimeSlotDeliveryRole.DELIVERY) or 0)
    remaining = round(scoped - scheduled, 1)
    return {
        "scoped": round(scoped, 1),
        "scheduled": round(scheduled, 1),
        "remaining": remaining,
        "over": remaining < 0,
        "over_by": round(-remaining, 1) if remaining < 0 else 0,
    }


def rank_candidates_for_phase(phase, *, required_working_days=None, search_start=None, candidate_pool=None, weights=None):
    """Derive inputs from a phase and rank its candidate deliverers.

    ``required_working_days`` / ``search_start`` may be supplied to override the
    values otherwise derived from the phase (scoped hours / desired start)."""
    today = timezone.now().date()
    required = required_working_days or phase_required_working_days(phase)
    search_start = search_start or phase.start_date or today
    if search_start < today:
        search_start = today

    # People already on the phase — booked (any slot) or assigned a named role.
    on_phase_ids = set(phase.timeslots.values_list("user_id", flat=True))
    on_phase_ids.discard(None)
    for uid in (phase.project_lead_id, phase.report_author_id, phase.techqa_by_id, phase.presqa_by_id):
        if uid:
            on_phase_ids.add(uid)

    # Their assigned roles (Lead / Author / Tech QA / Pres QA / AM …) for display.
    from .utils import assigned_role_map

    role_map = assigned_role_map(phase.job, phase) if phase.job_id else {}

    return rank_candidates_for_service(
        service=phase.service,
        required_working_days=required,
        search_start=search_start,
        search_end=search_start + timedelta(days=DEFAULT_HORIZON_DAYS),
        client=phase.job.client if phase.job_id else None,
        unit=phase.job.unit if phase.job_id else None,
        candidate_pool=candidate_pool,
        weights=weights,
        pinned_ids=on_phase_ids,
        role_map=role_map,
    )


def rank_candidates_for_job(job, *, required_working_days=None, candidate_pool=None, weights=None):
    """Job / indicative-services discovery: one ranked list per indicative service."""
    today = timezone.now().date()
    required = required_working_days or DEFAULT_JOB_DEFAULT_DAYS
    results = {}
    for service in job.indicative_services.all():
        results[service] = rank_candidates_for_service(
            service=service,
            required_working_days=required,
            search_start=today,
            search_end=today + timedelta(days=DEFAULT_HORIZON_DAYS),
            client=job.client,
            unit=job.unit,
            candidate_pool=candidate_pool,
            weights=weights,
        )
    return results


# --------------------------------------------------------------------------- #
# Split-team planner                                                           #
# --------------------------------------------------------------------------- #
#
# Once a scheduler has picked people from the suggestions, they draft how those
# people split the phase. Coverage is chosen per phase:
#   * sequential — testers cover the calendar span back-to-back (elapsed ≈ total)
#   * parallel   — testers work the same window (elapsed ≈ total / N)
# Defaults: Lead spans the whole phase and starts day one; Author takes the last
# block. Everything is editable before drafting.

DEFAULT_BUSINESS_DAYS = (1, 2, 3, 4, 5)  # Mon–Fri (weekday()+1 scheme)


def _is_working(d, business_days, holidays):
    return (d.weekday() + 1) in business_days and d not in holidays


def next_working_day(d, business_days=DEFAULT_BUSINESS_DAYS, holidays=frozenset()):
    """First working day on or after ``d``."""
    while not _is_working(d, business_days, holidays):
        d += timedelta(days=1)
    return d


def working_day_end(start, num_days, business_days=DEFAULT_BUSINESS_DAYS, holidays=frozenset()):
    """End date whose inclusive range from ``start`` covers ``num_days`` working
    days. ``start`` is assumed to already be a working day."""
    if num_days <= 1:
        return start
    counted = 1
    cur = start
    while counted < num_days:
        cur += timedelta(days=1)
        if _is_working(cur, business_days, holidays):
            counted += 1
    return cur


def count_working_days(start, end, business_days=DEFAULT_BUSINESS_DAYS, holidays=frozenset()):
    n, cur = 0, start
    while cur <= end:
        if _is_working(cur, business_days, holidays):
            n += 1
        cur += timedelta(days=1)
    return n


def allocate_man_days(total_days, n):
    """Split ``total_days`` man-days across ``n`` people as evenly as possible.
    Sum of the result always equals total_days (so the plan never over-utilises the
    scope). Larger shares come first (assigned to the lead / earliest testers)."""
    total_days = max(0, int(total_days))
    n = max(1, int(n))
    base, extra = divmod(total_days, n)
    return [base + 1] * extra + [base] * (n - extra)


def build_split_plan(
    *,
    user_ids,
    coverage,
    total_days,
    start_date,
    lead_id=None,
    author_id=None,
    business_days=DEFAULT_BUSINESS_DAYS,
    holidays=frozenset(),
):
    """Propose how the selected people split a phase's scoped **man-days**.

    The scope is person-days of effort, not calendar days: the per-person day
    allocations always **sum to total_days**, so the proposal never over-utilises.

    Args:
        user_ids: selected user ids, in ranked (preference) order.
        coverage: "sequential" (back-to-back, elapsed ≈ total) or "parallel"
            (concurrent, elapsed ≈ total / N; lead is present throughout).
        total_days: scoped delivery man-days to divide.
        start_date: desired team start (snapped to the next working day).
        lead_id / author_id: role designations (default: first / last; may be the
            same person → combined "lead_author" role).

    Returns a list of dicts (in display order):
        {user_id, role ('lead'|'author'|'lead_author'|'tester'), start, end, days}
    """
    ids = [int(u) for u in user_ids]
    if not ids:
        return []
    n = len(ids)
    total_days = max(1, int(total_days))

    if lead_id is None:
        lead_id = ids[0]
    lead_id = int(lead_id)
    if author_id is None:
        author_id = ids[0] if n == 1 else ids[-1]
    author_id = int(author_id)

    def role_of(uid):
        if uid == lead_id and uid == author_id:
            return "lead_author"
        if uid == lead_id:
            return "lead"
        if uid == author_id:
            return "author"
        return "tester"

    # Order: lead first, other testers in ranked order, author last (author may be
    # the lead, in which case there's no separate author row).
    others = [u for u in ids if u not in (lead_id, author_id)]
    ordered = [lead_id] + others
    if author_id != lead_id:
        ordered.append(author_id)
    seen = set()
    ordered = [u for u in ordered if not (u in seen or seen.add(u))]

    # Even man-day split (sum == total_days), largest shares first.
    allocs = allocate_man_days(total_days, len(ordered))
    days_by_user = dict(zip(ordered, allocs))

    start = next_working_day(start_date, business_days, holidays)
    plan = {}
    if coverage == "parallel":
        # Everyone works concurrently from the same start for their own share.
        for uid in ordered:
            d = days_by_user[uid]
            end = working_day_end(start, d, business_days, holidays) if d else start
            plan[uid] = (start, end, d)
    else:  # sequential — back-to-back, so the man-days lay out across the calendar
        cursor = start
        for uid in ordered:
            d = days_by_user[uid]
            seg_start = next_working_day(cursor, business_days, holidays)
            seg_end = working_day_end(seg_start, d, business_days, holidays) if d else seg_start
            plan[uid] = (seg_start, seg_end, d)
            if d:
                cursor = seg_end + timedelta(days=1)

    return [
        {
            "user_id": uid,
            "role": role_of(uid),
            "start": plan[uid][0],
            "end": plan[uid][1],
            "days": plan[uid][2],
        }
        for uid in ordered
    ]
