"""Support-team budget allocation engine.

Sibling to :mod:`chaotica_utils.utils.billing_allocation`. Answers *"of a job's
revenue, how much budget — in money, hours and days — does each back-office
support-team member get, and how much of it have they drawn down?"*

Like the billing-allocation engine this is a **read-only computed view**: it
never writes ``TimeSlot`` schedule bookings. The model (validated against the
Accenture MMP spreadsheet) is:

* **pool** ``= job.revenue × premium%`` — the premium resolves per-job override
  → unit default → constance ``SUPPORT_PREMIUM_DEFAULT``
  (see :meth:`Job.get_effective_premium`).
* each member has a **profile allocation %** (``100`` = full coverage, ``20`` =
  20%); their **share** ``= percent / Σ percents`` (so 6 @100 + 2 @20 ⇒ Σ 640, a
  100% member gets ``100/640 = 0.15625``).
* **budget money** ``= pool × share``; **hours** ``= budget_money / LCR`` (loaded
  cost rate per hour); **days** ``= hours / hours_in_day``.
* **remaining** is tracked in **money**: ``budget_money − Σ draw money`` (each
  draw records the LCR it was cashed out at, so a later rate change never
  re-prices past draws). It is shown in hours at the *current* LCR and carries
  forward across periods. Cash-outs are created only via
  :func:`create_support_draw`, which refuses to exceed the remaining budget.

All money/hour maths is done in :class:`~decimal.Decimal` for exact shares;
guards return warnings (never divide-by-zero) when revenue, weights or a
member's loaded cost rate are missing.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

#: Email of the sentinel user that deleted accounts are re-pointed to
#: (see :func:`chaotica_utils.utils.common.get_sentinel_user`).
SENTINEL_EMAIL = "deleted@chaotica.app"

#: Tolerance (hours) for rounding when checking a cash-out against remaining.
DRAW_TOLERANCE_HOURS = Decimal("0.005")


def fmt_decimal(value):
    """Render a percent/hours Decimal for messages: ``20``, ``20.5``, ``7.5``
    (no trailing zeros, never exponent notation)."""
    if value is None:
        return "0"
    value = Decimal(value).normalize()
    return format(value, "f")


def support_draw_message(user, draw):
    """Audit-trail text for a cash-out (same wording on every entry point)."""
    return "{user} cashed out {hrs}h of support budget ({start} - {end}).".format(
        user=user,
        hrs=fmt_decimal(draw.hours_drawn),
        start=draw.period_start,
        end=draw.period_end,
    )


def _is_real_member(row):
    """A support row that can hold (and draw) a share: has a live user."""
    return row.user_id is not None and row.user.email != SENTINEL_EMAIL


def resolve_lcr(user, on_date):
    """Loaded cost rate (per hour) for ``user`` effective on ``on_date``.

    Thin wrapper over :meth:`UserCost.cost_on` (date-aware). Returns a Decimal
    or ``None`` when the user has no applicable cost row.
    """
    from chaotica_utils.models import UserCost

    return UserCost.cost_on(user, on_date)


def resolve_lcrs(user_ids, on_date):
    """Batched :func:`resolve_lcr`: ``{user_id: Decimal | None}`` in one query.

    Same rule as :meth:`UserCost.cost_on`: the latest row effective on or
    before ``on_date``, else the newest undated row.
    """
    from chaotica_utils.models import UserCost

    dated, undated = {}, {}
    for user_id, effective_from, cost in (
        UserCost.objects.filter(user_id__in=set(user_ids))
        .filter(Q(effective_from__lte=on_date) | Q(effective_from__isnull=True))
        .order_by("user_id", "-effective_from", "-pk")
        .values_list("user_id", "effective_from", "cost_per_hour")
    ):
        if effective_from is None:
            undated.setdefault(user_id, cost)
        else:
            dated.setdefault(user_id, cost)
    return {
        uid: dated[uid] if uid in dated else undated.get(uid) for uid in set(user_ids)
    }


def _draw_totals(draws_qs):
    """``{support_role_id: (hours, money)}`` summed over ``draws_qs``."""
    from django.db.models import Sum

    return {
        d["support_role_id"]: (
            d["hours"] or Decimal("0"),
            d["money"] or Decimal("0"),
        )
        for d in draws_qs.values("support_role_id").annotate(
            hours=Sum("hours_drawn"), money=Sum("money_drawn")
        )
    }


def _has_weekday(start, end):
    from datetime import timedelta

    day = start
    for _ in range(7):
        if day > end:
            return False
        if day.weekday() < 5:
            return True
        day += timedelta(days=1)
    return True


def _hours_in_day(job):
    try:
        return Decimal(str(job.get_hours_in_day()))
    except Exception:
        from django.conf import settings

        return Decimal(str(settings.DEFAULT_HOURS_IN_DAY))


def build_job_support_budget(
    job, on_date=None, *, support_rows=None, draw_totals=None, lcrs=None
):
    """Compute the support-team budget for a single job.

    Returns::

        {
          "pool": Decimal,            # money reserved for the support pool
          "premium": Decimal,         # % applied (e.g. Decimal("8"))
          "revenue": Decimal,         # job revenue used as the base
          "percent_sum": Decimal,     # Σ profile allocation % of active members
          "hours_in_day": Decimal,
          "per_member": {user_id: {
              "user", "role_id", "role", "profile_percent", "share",
              "share_percent", "budget_money", "lcr", "budget_hours",
              "budget_days", "drawn_hours", "drawn_money",
              "remaining_money", "remaining_hours",
          }},
          "warnings": [str, ...],
        }

    ``budget_hours``/``budget_days``/``remaining_hours`` are ``None`` for a
    member with no loaded cost rate (money is still computed). Hours are
    valued at the LCR on ``on_date`` (default today); remaining is tracked in
    money so past draws keep the rate they were cashed out at. Rows without a
    live user (null / deleted-user sentinel) are excluded from the split.

    ``support_rows`` (the job's support rows, user loaded), ``draw_totals``
    (``{role_id: (hours, money)}``) and ``lcrs`` (``{user_id: rate}``) can be
    pre-loaded by a caller building many jobs at once; otherwise each is
    queried here.
    """
    from datetime import date as date_cls

    if on_date is None:
        on_date = date_cls.today()

    warnings = []
    revenue = Decimal(job.revenue) if job.revenue is not None else Decimal("0")
    premium = job.get_effective_premium()
    pool = revenue * premium / Decimal("100")
    hours_in_day = _hours_in_day(job)

    if revenue == 0:
        warnings.append("Job has no revenue set — all support budgets are zero.")

    if support_rows is None:
        support_rows = job.supporting_team.select_related("user").all()
    all_rows = list(support_rows)
    rows = [r for r in all_rows if _is_real_member(r)]
    if len(rows) != len(all_rows):
        warnings.append(
            "{} support row(s) have no live user and are excluded from the "
            "split.".format(len(all_rows) - len(rows))
        )
    percent_sum = sum((r.profile_percent for r in rows), Decimal("0"))
    if percent_sum == 0 and rows:
        warnings.append(
            "Support profile allocations sum to zero — cannot split the pool."
        )

    # Pre-load ledger draws per support role in one query.
    from jobtracker.models.job import SupportBudgetDraw

    if draw_totals is None:
        draw_totals = _draw_totals(SupportBudgetDraw.objects.filter(support_role__job=job))
    if lcrs is None:
        lcrs = resolve_lcrs([r.user_id for r in rows], on_date)

    per_member = {}
    for row in rows:
        share = (row.profile_percent / percent_sum) if percent_sum else Decimal("0")
        budget_money = pool * share
        lcr = lcrs.get(row.user_id)
        drawn, drawn_money = draw_totals.get(row.id, (Decimal("0"), Decimal("0")))
        remaining_money = budget_money - drawn_money
        if lcr is None or lcr == 0:
            warnings.append(
                "{} has no loaded cost rate — hours cannot be derived.".format(
                    row.user
                )
            )
            budget_hours = None
            budget_days = None
            remaining_hours = None
        else:
            budget_hours = budget_money / lcr
            budget_days = (
                budget_hours / hours_in_day if hours_in_day else None
            )
            remaining_hours = remaining_money / lcr
        per_member[row.user_id] = {
            "user": row.user,
            "role_id": row.id,
            "role": row.role,
            "profile_percent": row.profile_percent,
            "share": share,
            "share_percent": share * Decimal("100"),
            "budget_money": budget_money,
            "lcr": lcr,
            "budget_hours": budget_hours,
            "budget_days": budget_days,
            "drawn_hours": drawn,
            "drawn_money": drawn_money,
            "remaining_money": remaining_money,
            "remaining_hours": remaining_hours,
        }

    return {
        "pool": pool,
        "premium": premium,
        "revenue": revenue,
        "percent_sum": percent_sum,
        "hours_in_day": hours_in_day,
        "per_member": per_member,
        "warnings": warnings,
    }


def build_user_support_budget(user, start=None, end=None):
    """Roll up a single user's support budget across their drawable jobs.

    Returns ``{"per_job": [...], "totals": {budget_money, budget_hours,
    drawn_hours, remaining_hours}, "has_remaining": bool, "warnings": [...]}``.
    Draws are filtered to ``[start, end]`` when provided (so a page can show
    "this period"), while the budget itself reflects the whole job. Valuation
    always uses today's LCR — the viewed period never changes the rate.
    """
    from jobtracker.models.job import JobSupportTeamRole, SupportBudgetDraw
    from jobtracker.enums import JobStatuses

    roles = (
        JobSupportTeamRole.objects.filter(user=user)
        .filter(job__status__in=JobStatuses.SUPPORT_DRAWABLE_STATUSES)
        .select_related("job", "job__unit", "job__client", "job__support_profile")
    )

    per_job = []
    totals = {
        "budget_money": Decimal("0"),
        "budget_hours": Decimal("0"),
        "drawn_hours": Decimal("0"),
        "remaining_hours": Decimal("0"),
    }
    has_remaining = False
    warnings = []

    # Batch everything the per-job builds need: a fixed number of queries
    # however many support roles the user holds.
    from datetime import date as date_cls
    from jobtracker.models.job import JobSupportTeamRole as Row

    roles = list(roles)
    job_ids = [r.job_id for r in roles]
    rows_by_job = {}
    for row in Row.objects.filter(job_id__in=job_ids).select_related("user"):
        rows_by_job.setdefault(row.job_id, []).append(row)
    all_draw_totals = _draw_totals(
        SupportBudgetDraw.objects.filter(support_role__job_id__in=job_ids)
    )
    today = date_cls.today()
    lcrs = resolve_lcrs(
        [r.user_id for rows in rows_by_job.values() for r in rows if r.user_id],
        today,
    )
    period_draws = SupportBudgetDraw.objects.filter(
        support_role_id__in=[r.pk for r in roles]
    )
    if start is not None:
        period_draws = period_draws.filter(period_end__gte=start)
    if end is not None:
        period_draws = period_draws.filter(period_start__lte=end)
    period_drawn_by_role = {
        role_id: hours for role_id, (hours, _money) in _draw_totals(period_draws).items()
    }

    for role in roles:
        budget = build_job_support_budget(
            role.job,
            today,
            support_rows=rows_by_job.get(role.job_id, []),
            draw_totals=all_draw_totals,
            lcrs=lcrs,
        )
        member = budget["per_member"].get(user.id)
        if member is None:
            continue
        warnings.extend(
            "{}: {}".format(role.job, w) for w in budget["warnings"]
        )

        period_drawn = period_drawn_by_role.get(role.pk, Decimal("0"))

        remaining = member["remaining_hours"]
        if remaining is not None and remaining > DRAW_TOLERANCE_HOURS:
            has_remaining = True

        entry = {
            "job": role.job,
            "role": role,
            "budget_money": member["budget_money"],
            "lcr": member["lcr"],
            "budget_hours": member["budget_hours"],
            "budget_days": member["budget_days"],
            "drawn_hours": member["drawn_hours"],
            "period_drawn_hours": period_drawn,
            "remaining_hours": remaining,
        }
        per_job.append(entry)

        totals["budget_money"] += member["budget_money"]
        if member["budget_hours"] is not None:
            totals["budget_hours"] += member["budget_hours"]
        totals["drawn_hours"] += member["drawn_hours"]
        if remaining is not None:
            totals["remaining_hours"] += remaining

    return {
        "per_job": per_job,
        "totals": totals,
        "has_remaining": has_remaining,
        "warnings": warnings,
    }


def _role_member(role):
    """This role's ``per_member`` entry from its job's budget (or None)."""
    member = build_job_support_budget(role.job)["per_member"].get(role.user_id)
    if member is None or member["role_id"] != role.id:
        return None
    return member


def remaining_hours_for_role(role):
    """Remaining cash-out hours for one support role at today's LCR (or None)."""
    member = _role_member(role)
    return member["remaining_hours"] if member else None


def create_support_draw(
    role,
    period_start,
    period_end,
    hours=None,
    created_by=None,
    fill_remaining=False,
    max_hours=None,
):
    """Cash out ``hours`` of a support role's budget — the ONLY write path.

    Locks the role row, re-computes the remaining budget and refuses anything
    that would overdraw it. With ``fill_remaining`` the draw is whatever
    remains (rounded down to 0.01h, and capped at ``max_hours`` if given),
    worked out under the same lock. Each draw
    records the LCR it was cashed out at (today's rate — never a user-chosen
    date) and its money value, so a later rate change never re-prices it.
    Raises :class:`ValidationError` (with field keys where applicable) on any
    rule failure.
    """
    from datetime import date as date_cls
    from jobtracker.enums import JobStatuses
    from jobtracker.models.job import JobSupportTeamRole, SupportBudgetDraw

    if not fill_remaining:
        hours = Decimal(hours)
        if hours <= 0:
            raise ValidationError({"hours_drawn": "Hours must be greater than zero."})
    if period_start and period_end and period_start > period_end:
        raise ValidationError(
            {"period_end": "The period end must be on or after its start."}
        )
    if period_start and period_start > date_cls.today():
        # Cash-outs record time already (being) worked: current or past
        # periods only.
        raise ValidationError(
            {"period_start": "Support can't be cashed out for a future period."}
        )
    if period_start and period_end and not _has_weekday(period_start, period_end):
        # The timesheet spreads draws over weekdays; a weekend-only period
        # would use budget without ever showing on it.
        raise ValidationError(
            {"period_end": "The period must include at least one weekday."}
        )

    with transaction.atomic():
        # Serialise concurrent cash-outs on the same role (double-clicks, two
        # tabs, auto + manual) so the remaining check can't be raced.
        role = (
            JobSupportTeamRole.objects.select_for_update()
            .select_related(
                "job", "job__client", "job__unit", "job__support_profile", "user"
            )
            .get(pk=role.pk)
        )
        if role.job.status not in JobStatuses.SUPPORT_DRAWABLE_STATUSES:
            raise ValidationError(
                "Support budget can't be cashed out on a job that is {}.".format(
                    role.job.get_status_display()
                )
            )
        if not _is_real_member(role):
            raise ValidationError("This support role has no live user.")

        # One budget build gives both today's LCR and what's left.
        member = _role_member(role)
        lcr = member["lcr"] if member else resolve_lcr(role.user, date_cls.today())
        if not lcr:
            raise ValidationError(
                "{} has no loaded cost rate, so hours can't be cashed out.".format(
                    role.user
                )
            )
        remaining = member["remaining_hours"] if member else None
        if fill_remaining:
            hours = remaining or Decimal("0")
            if max_hours is not None:
                hours = min(hours, Decimal(max_hours))
            hours = hours.quantize(Decimal("0.01"), rounding="ROUND_DOWN")
            if hours <= 0:
                raise ValidationError({"hours_drawn": "Nothing left to cash out."})
        if remaining is None or hours > remaining + DRAW_TOLERANCE_HOURS:
            raise ValidationError(
                {
                    "hours_drawn": "Only {}h remaining to cash out.".format(
                        max(remaining or Decimal("0"), Decimal("0")).quantize(
                            Decimal("0.01")
                        )
                    )
                }
            )

        from jobtracker.models.job import SupportDrawDay

        # Plan the timesheet days before writing, so it sees only what was
        # already there.
        plan = plan_draw_days(role.user, period_start, period_end, hours)
        draw = SupportBudgetDraw.objects.create(
            support_role=role,
            user=role.user,
            period_start=period_start,
            period_end=period_end,
            hours_drawn=hours,
            lcr_at_draw=lcr,
            money_drawn=(hours * lcr).quantize(Decimal("0.01")),
            created_by=created_by,
        )
        SupportDrawDay.objects.bulk_create(
            SupportDrawDay(draw=draw, day=day, hours=h) for day, h in plan.items()
        )
        return draw


def plan_draw_days(user, period_start, period_end, hours):
    """Lay ``hours`` of support on the period's weekdays as whole days.

    Fills each day's free time (hours per day less everything already on the
    timesheet that day, including earlier support) in date order, so a
    cash-out reads like a timesheet: full days on one code, not a sliver
    every day. Anything beyond the free time is spread evenly over the
    weekdays. Returns ``{date: Decimal}`` summing exactly to ``hours``.
    """
    from datetime import timedelta
    from constance import config
    from .billing_allocation import build_user_code_allocation

    cent = Decimal("0.01")
    hours = Decimal(hours).quantize(cent)
    weekdays = []
    day = period_start
    while day <= period_end:
        if day.weekday() < 5:
            weekdays.append(day)
        day += timedelta(days=1)
    if not weekdays or hours <= 0:
        return {}

    per_day = build_user_code_allocation(user, period_start, period_end)["per_day"]
    day_cap = Decimal(str(config.DEFAULT_HOURS_IN_DAY))
    plan = {}
    left = hours
    for day in weekdays:
        if left <= 0:
            break
        used = sum((e["hours"] for e in per_day.get(day, [])), Decimal("0"))
        free = (day_cap - used).quantize(cent, rounding="ROUND_DOWN")
        if free <= 0:
            continue
        take = min(free, left)
        plan[day] = take
        left -= take
    if left > 0:
        # More than the free time (a manual cash-out): spread the rest evenly,
        # the last day taking the rounding.
        each = (left / len(weekdays)).quantize(cent, rounding="ROUND_DOWN")
        for i, day in enumerate(weekdays):
            add = each if i < len(weekdays) - 1 else left - each * (len(weekdays) - 1)
            plan[day] = plan.get(day, Decimal("0")) + add
    return {d: h for d, h in plan.items() if h > 0}


def free_hours_in_period(user, period_start, period_end, stats=None):
    """Hours of ``user``'s period not already on their timesheet: capacity less
    booked work (coded or not), leave/holidays, internal time and support
    already cashed out. Never negative. ``stats`` can be passed by a caller
    that already built the period's allocation."""
    if stats is None:
        from .billing_allocation import build_user_code_allocation

        stats = build_user_code_allocation(user, period_start, period_end)["stats"]
    free = (
        stats["capacity_hours"] - stats["scheduled_hours"] - stats["support_hours"]
    )
    return max(Decimal(free), Decimal("0"))


def auto_cash_out(user, period_start, period_end, created_by=None):
    """Fill the period's free hours from ``user``'s support budgets.

    Jobs are used oldest first, each up to its remaining budget, until the
    free hours (see :func:`free_hours_in_period`) run out. A second run finds
    no free hours left. Each draw goes through :func:`create_support_draw`.
    Returns the list of created draws.
    """
    from jobtracker.enums import JobStatuses
    from jobtracker.models.job import JobSupportTeamRole
    from chaotica_utils.models import User

    created = []
    with transaction.atomic():
        # Serialise auto runs for this person (double-clicks, two tabs) so
        # two runs can't both see the same free hours.
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        left = free_hours_in_period(user, period_start, period_end).quantize(
            Decimal("0.01"), rounding="ROUND_DOWN"
        )
        if left <= 0:
            return created
        roles = (
            JobSupportTeamRole.objects.filter(
                user=user, job__status__in=JobStatuses.SUPPORT_DRAWABLE_STATUSES
            )
            .order_by("job__id", "job__db_id", "pk")
            .only("pk")
        )
        for role in roles:
            if left <= 0:
                break
            # The remaining budget is read under the role lock, so each role's
            # budget is built once and can't be raced.
            try:
                draw = create_support_draw(
                    role,
                    period_start,
                    period_end,
                    created_by=created_by,
                    fill_remaining=True,
                    max_hours=left,
                )
            except ValidationError:
                # Nothing left, no LCR, or no longer eligible — skip.
                continue
            created.append(draw)
            left -= draw.hours_drawn
    return created
