"""Job detail data shared by the job page and /api/v1/jobs/."""

from decimal import Decimal

from ..enums import JobStatuses, PhaseStatuses

# Scoped effort categories, in display order.
EFFORT_FIELDS = (
    ("Delivery", "delivery_hours"),
    ("Reporting", "reporting_hours"),
    ("Management", "mgmt_hours"),
    ("QA", "qa_hours"),
    ("Oversight", "oversight_hours"),
    ("Debrief", "debrief_hours"),
    ("Contingency", "contingency_hours"),
    ("Other", "other_hours"),
)


def job_warnings(job):
    """The badges shown under a job's title (``partials/job/warnings.html``)."""
    out = []
    if job.is_restricted:
        out.append(f"Restricted: {job.get_restricted_detail_display()}")
    if job.high_risk:
        out.append("High Risk")
    if job.technically_complex_test:
        out.append("Complex Job")
    if job.is_time_limited:
        out.append("Time Limited")
    if job.is_imported:
        out.append("Imported")
    return out


def phases_missing_billing_code(job):
    """Live phases with no billing code of their own on a job with none."""
    if (
        job.status in JobStatuses.CLOSED_STATUSES
        or job.billing_code_assignments.exists()
    ):
        return []
    return [
        p
        for p in job.phases.all()
        if p.status not in PhaseStatuses.INACTIVE_STATUSES
        and not p.billing_code_assignments.all()
    ]


def can_view_loaded_costs(user, job):
    return user.is_superuser or bool(
        job.unit_id and user.has_perm("jobtracker.can_view_loaded_costs", job.unit)
    )


def job_sales_summary(job, include_costs=True):
    """Everything on the job Sales tab. Callers decide what to show: staff
    cost / profit / support money are finance data (see the API). Without
    ``include_costs`` the (costly) staff cost isn't computed and reads 0."""
    revenue = Decimal(job.revenue or 0)
    staff_cost = Decimal(str(job.staff_cost() or 0)) if include_costs else Decimal(0)
    profit = revenue - staff_cost
    # Defensive: the model properties divide by revenue / scoped days.
    profit_perc = round(profit / revenue * 100, 1) if revenue else Decimal(0)
    target_profit = Decimal(job.unit.targetProfit) if job.unit_id else Decimal(0)
    scoped_days = Decimal(str(job.get_total_scoped_days() or 0))
    support = job.get_support_budget()
    phases = list(job.phases.all())
    effort = []
    for label, field in EFFORT_FIELDS:
        total = sum((getattr(p, field, 0) or Decimal(0)) for p in phases)
        if total:
            effort.append({"label": label, "hours": total})
    return {
        "revenue": revenue,
        "staff_cost": staff_cost,
        "profit": profit,
        "profit_perc": profit_perc,
        "target_profit": target_profit,
        "meets_target": profit_perc >= target_profit,
        "scoped_days": scoped_days,
        "avg_day_rate": round(revenue / scoped_days, 2) if scoped_days else Decimal(0),
        "support_pool": support["pool"],
        "support_premium": support["premium"],
        "support_members": sorted(
            support["per_member"].values(),
            key=lambda m: m["budget_money"],
            reverse=True,
        ),
        "effort": effort,
    }


def job_support_roles(job, viewer, can_view_money, support_budget=None):
    """Support-team roles with each member's computed budget attached
    (``role.budget``) and whether ``viewer`` may cash out (``role.can_cash_out``,
    same rule as ``can_cash_out_support_role``)."""
    per_member = (support_budget or job.get_support_budget())["per_member"]
    roles = list(job.supporting_team.select_related("user").all())
    for role in roles:
        role.budget = per_member.get(role.user_id)
        role.can_cash_out = (
            viewer.is_superuser
            or can_view_money
            or bool(role.user_id and role.user.can_be_managed_by(viewer))
        )
    return roles
