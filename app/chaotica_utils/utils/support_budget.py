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
* **remaining** ``= budget_hours − Σ ledger draws`` (carries forward per period).

All money/hour maths is done in :class:`~decimal.Decimal` for exact shares;
guards return warnings (never divide-by-zero) when revenue, weights or a
member's loaded cost rate are missing.
"""

from decimal import Decimal


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
              "role", "profile_percent", "share", "share_percent",
              "budget_money", "lcr", "budget_hours", "budget_days",
              "drawn_hours", "remaining_hours",
          }},
          "warnings": [str, ...],
        }

    ``budget_hours``/``budget_days``/``remaining_hours`` are ``None`` for a
    member with no loaded cost rate (money is still computed).
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

    rows = list(job.supporting_team.select_related("user").all())
    percent_sum = sum((r.profile_percent for r in rows), Decimal("0"))
    if percent_sum == 0 and rows:
        warnings.append(
            "Support profile allocations sum to zero — cannot split the pool."
        )

    # Pre-load ledger draws per support role in one query.
    from django.db.models import Sum
    from jobtracker.models.job import SupportBudgetDraw

    draw_totals = {
        d["support_role_id"]: d["total"] or Decimal("0")
        for d in SupportBudgetDraw.objects.filter(support_role__job=job)
        .values("support_role_id")
        .annotate(total=Sum("hours_drawn"))
    }

    per_member = {}
    for row in rows:
        share = (row.profile_percent / percent_sum) if percent_sum else Decimal("0")
        budget_money = pool * share
        lcr = resolve_lcr(row.user, on_date)
        drawn = draw_totals.get(row.id, Decimal("0"))
        if lcr is None or lcr == 0:
            if row.user_id is not None:
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
            remaining_hours = budget_hours - drawn
        per_member[row.user_id] = {
            "role": row.role,
            "profile_percent": row.profile_percent,
            "share": share,
            "share_percent": share * Decimal("100"),
            "budget_money": budget_money,
            "lcr": lcr,
            "budget_hours": budget_hours,
            "budget_days": budget_days,
            "drawn_hours": drawn,
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
    """Roll up a single user's support budget across their active jobs.

    Returns ``{"per_job": [...], "totals": {budget_money, budget_hours,
    drawn_hours, remaining_hours}, "warnings": [...]}``. Draws are filtered to
    ``[start, end]`` when provided (so a page can show "this period"), while the
    budget itself reflects the whole job.
    """
    from jobtracker.models.job import JobSupportTeamRole, SupportBudgetDraw
    from jobtracker.enums import JobStatuses

    roles = (
        JobSupportTeamRole.objects.filter(user=user)
        .filter(job__status__in=JobStatuses.ACTIVE_STATUSES)
        .select_related("job", "job__unit", "job__client")
    )

    per_job = []
    totals = {
        "budget_money": Decimal("0"),
        "budget_hours": Decimal("0"),
        "drawn_hours": Decimal("0"),
        "remaining_hours": Decimal("0"),
    }
    warnings = []
    for role in roles:
        budget = build_job_support_budget(role.job, on_date=end)
        member = budget["per_member"].get(user.id)
        if member is None:
            continue

        draws_qs = SupportBudgetDraw.objects.filter(support_role=role)
        if start is not None:
            draws_qs = draws_qs.filter(period_end__gte=start)
        if end is not None:
            draws_qs = draws_qs.filter(period_start__lte=end)
        period_drawn = sum(
            (d.hours_drawn for d in draws_qs), Decimal("0")
        )

        entry = {
            "job": role.job,
            "role": role,
            "budget_money": member["budget_money"],
            "lcr": member["lcr"],
            "budget_hours": member["budget_hours"],
            "budget_days": member["budget_days"],
            "drawn_hours": member["drawn_hours"],
            "period_drawn_hours": period_drawn,
            "remaining_hours": member["remaining_hours"],
        }
        per_job.append(entry)

        totals["budget_money"] += member["budget_money"]
        if member["budget_hours"] is not None:
            totals["budget_hours"] += member["budget_hours"]
        totals["drawn_hours"] += member["drawn_hours"]
        if member["remaining_hours"] is not None:
            totals["remaining_hours"] += member["remaining_hours"]

    return {"per_job": per_job, "totals": totals, "warnings": warnings}
