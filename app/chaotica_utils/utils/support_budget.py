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

#: Email of the sentinel user that deleted accounts are re-pointed to
#: (see :func:`chaotica_utils.utils.common.get_sentinel_user`).
SENTINEL_EMAIL = "deleted@chaotica.app"

#: Tolerance (hours) for rounding when checking a cash-out against remaining.
DRAW_TOLERANCE_HOURS = Decimal("0.005")


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


def _hours_in_day(job):
    try:
        return Decimal(str(job.get_hours_in_day()))
    except Exception:
        from django.conf import settings

        return Decimal(str(settings.DEFAULT_HOURS_IN_DAY))


def build_job_support_budget(job, on_date=None):
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

    all_rows = list(job.supporting_team.select_related("user").all())
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
    from django.db.models import Sum
    from jobtracker.models.job import SupportBudgetDraw

    draw_totals = {
        d["support_role_id"]: (
            d["hours"] or Decimal("0"),
            d["money"] or Decimal("0"),
        )
        for d in SupportBudgetDraw.objects.filter(support_role__job=job)
        .values("support_role_id")
        .annotate(hours=Sum("hours_drawn"), money=Sum("money_drawn"))
    }

    per_member = {}
    for row in rows:
        share = (row.profile_percent / percent_sum) if percent_sum else Decimal("0")
        budget_money = pool * share
        lcr = resolve_lcr(row.user, on_date)
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
        .select_related("job", "job__unit", "job__client")
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
    for role in roles:
        budget = build_job_support_budget(role.job)
        member = budget["per_member"].get(user.id)
        if member is None:
            continue
        warnings.extend(
            "{}: {}".format(role.job, w) for w in budget["warnings"]
        )

        draws_qs = SupportBudgetDraw.objects.filter(support_role=role)
        if start is not None:
            draws_qs = draws_qs.filter(period_end__gte=start)
        if end is not None:
            draws_qs = draws_qs.filter(period_start__lte=end)
        period_drawn = sum(
            (d.hours_drawn for d in draws_qs), Decimal("0")
        )

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


def remaining_hours_for_role(role):
    """Remaining cash-out hours for one support role at today's LCR (or None)."""
    budget = build_job_support_budget(role.job)
    member = budget["per_member"].get(role.user_id)
    if member is None or member["role_id"] != role.id:
        return None
    return member["remaining_hours"]


def create_support_draw(role, period_start, period_end, hours, created_by=None):
    """Cash out ``hours`` of a support role's budget — the ONLY write path.

    Locks the role row, re-computes the remaining budget and refuses anything
    that would overdraw it. Each draw records the LCR it was cashed out at
    (today's rate — never a user-chosen date) and its money value, so a later
    rate change never re-prices it. Raises :class:`ValidationError` (with
    field keys where applicable) on any rule failure.
    """
    from datetime import date as date_cls
    from jobtracker.enums import JobStatuses
    from jobtracker.models.job import JobSupportTeamRole, SupportBudgetDraw

    hours = Decimal(hours)
    if hours <= 0:
        raise ValidationError({"hours_drawn": "Hours must be greater than zero."})
    if period_start and period_end and period_start > period_end:
        raise ValidationError(
            {"period_end": "The period end must be on or after its start."}
        )

    with transaction.atomic():
        # Serialise concurrent cash-outs on the same role (double-clicks, two
        # tabs, auto + manual) so the remaining check can't be raced.
        role = (
            JobSupportTeamRole.objects.select_for_update()
            .select_related("job", "user")
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

        lcr = resolve_lcr(role.user, date_cls.today())
        if not lcr:
            raise ValidationError(
                "{} has no loaded cost rate, so hours can't be cashed out.".format(
                    role.user
                )
            )
        remaining = remaining_hours_for_role(role)
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

        return SupportBudgetDraw.objects.create(
            support_role=role,
            user=role.user,
            period_start=period_start,
            period_end=period_end,
            hours_drawn=hours,
            lcr_at_draw=lcr,
            money_drawn=(hours * lcr).quantize(Decimal("0.01")),
            created_by=created_by,
        )


def auto_cash_out(user, period_start, period_end, created_by=None):
    """Top up every drawable support role of ``user`` with its remaining budget.

    Idempotent by construction: each draw goes through
    :func:`create_support_draw`, so a second run finds nothing remaining.
    Returns the list of created draws.
    """
    from jobtracker.enums import JobStatuses
    from jobtracker.models.job import JobSupportTeamRole

    created = []
    roles = JobSupportTeamRole.objects.filter(
        user=user, job__status__in=JobStatuses.SUPPORT_DRAWABLE_STATUSES
    ).select_related("job")
    for role in roles:
        remaining = remaining_hours_for_role(role)
        if remaining is None:
            continue
        hours = remaining.quantize(Decimal("0.01"), rounding="ROUND_DOWN")
        if hours <= 0:
            continue
        try:
            created.append(
                create_support_draw(
                    role, period_start, period_end, hours, created_by=created_by
                )
            )
        except ValidationError:
            # Raced to zero / became ineligible between read and lock — skip.
            continue
    return created
