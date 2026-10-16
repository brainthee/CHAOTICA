"""Client-side data shared by the client pages and /api/v1/."""

from decimal import Decimal

from django.utils import timezone

from chaotica_utils.utils import slots_to_days as _calc_days

from ..enums import TimeSlotDeliveryRole
from ..models import TimeSlot


def framework_usage(fw, now=None):
    """Days used / scheduled / left on a framework, broken down by job and
    phase, person, delivery role, service and month. Also sets
    ``fw.computed_*`` for the summary tiles."""
    usage = {}
    now = now or timezone.now()
    hours_in_day = fw.get_hours_in_day()

    all_slots = list(
        TimeSlot.objects.filter(phase__job__associated_framework=fw)
        .select_related("user", "phase", "phase__job", "phase__service")
        .prefetch_related("user__unit_memberships__unit")
    )

    # Pre-compute business hours once per slot to avoid repeated calculation
    for slot in all_slots:
        slot._cached_hours = slot.get_business_hours()

    # Pre-compute summary stats so the template doesn't call model methods
    # (which would each re-query the database independently)
    fw.computed_days_used = _calc_days(all_slots, hours_in_day, lambda s: s.end < now)
    fw.computed_days_scheduled = _calc_days(
        all_slots, hours_in_day, lambda s: s.start >= now
    )
    fw.computed_days_available = (
        fw.total_days - fw.computed_days_used - fw.computed_days_scheduled
    )
    fw.computed_is_over_allocated = (
        fw.computed_days_used + fw.computed_days_scheduled
    ) > fw.total_days

    usage["TimeSlotDeliveryRoles"] = TimeSlotDeliveryRole.CHOICES

    # Per-job data with phase breakdown
    jobs_data = []
    for job in fw.associated_jobs.all().prefetch_related("phases"):
        job_slots = [s for s in all_slots if s.phase.job_id == job.pk]
        job_entry = {
            "job": job,
            "used_days": _calc_days(job_slots, hours_in_day, lambda s: s.end < now),
            "scheduled_days": _calc_days(
                job_slots, hours_in_day, lambda s: s.start >= now
            ),
            "total_days": _calc_days(job_slots, hours_in_day),
            "phases": [],
        }
        for phase in job.phases.all():
            phase_slots = [s for s in job_slots if s.phase_id == phase.pk]
            if phase_slots:
                job_entry["phases"].append(
                    {
                        "phase": phase,
                        "used_days": _calc_days(
                            phase_slots, hours_in_day, lambda s: s.end < now
                        ),
                        "scheduled_days": _calc_days(
                            phase_slots, hours_in_day, lambda s: s.start >= now
                        ),
                        "total_days": _calc_days(phase_slots, hours_in_day),
                    }
                )
        jobs_data.append(job_entry)
    usage["jobs_data"] = jobs_data

    # Per-user breakdown
    users_data = []
    users_by_id = {}
    for s in all_slots:
        if s.user_id not in users_by_id:
            users_by_id[s.user_id] = {"user": s.user, "slots": []}
        users_by_id[s.user_id]["slots"].append(s)
    for data in users_by_id.values():
        users_data.append(
            {
                "user": data["user"],
                "used_days": _calc_days(
                    data["slots"], hours_in_day, lambda s: s.end < now
                ),
                "scheduled_days": _calc_days(
                    data["slots"], hours_in_day, lambda s: s.start >= now
                ),
                "total_days": _calc_days(data["slots"], hours_in_day),
            }
        )
    users_data.sort(key=lambda x: x["total_days"], reverse=True)
    usage["users_data"] = users_data

    # Per-delivery-role breakdown
    roles_data = []
    for role_val, role_name in TimeSlotDeliveryRole.CHOICES:
        if role_val == 0:
            continue
        role_slots = [s for s in all_slots if s.deliveryRole == role_val]
        if role_slots:
            roles_data.append(
                {
                    "role_name": role_name,
                    "used_days": _calc_days(
                        role_slots, hours_in_day, lambda s: s.end < now
                    ),
                    "scheduled_days": _calc_days(
                        role_slots, hours_in_day, lambda s: s.start >= now
                    ),
                    "total_days": _calc_days(role_slots, hours_in_day),
                }
            )
    usage["roles_data"] = roles_data

    # Totals for the roles breakdown footer
    usage["roles_total_used"] = _calc_days(
        all_slots, hours_in_day, lambda s: s.end < now
    )
    usage["roles_total_scheduled"] = _calc_days(
        all_slots, hours_in_day, lambda s: s.start >= now
    )
    usage["roles_total"] = _calc_days(all_slots, hours_in_day)

    # Per-service breakdown
    services_by_id = {}
    for s in all_slots:
        svc = s.phase.service
        if svc is None:
            continue
        if svc.pk not in services_by_id:
            services_by_id[svc.pk] = {"service": svc, "slots": []}
        services_by_id[svc.pk]["slots"].append(s)
    services_data = []
    for data in services_by_id.values():
        services_data.append(
            {
                "service": data["service"],
                "used_days": _calc_days(
                    data["slots"], hours_in_day, lambda s: s.end < now
                ),
                "scheduled_days": _calc_days(
                    data["slots"], hours_in_day, lambda s: s.start >= now
                ),
                "total_days": _calc_days(data["slots"], hours_in_day),
            }
        )
    services_data.sort(key=lambda x: x["total_days"], reverse=True)
    usage["services_data"] = services_data

    # Monthly burn-down data (days consumed per month)
    monthly = {}
    for s in all_slots:
        if s.end >= now:
            continue
        month_key = s.start.strftime("%Y-%m")
        if month_key not in monthly:
            monthly[month_key] = []
        monthly[month_key].append(s)
    monthly_data = []
    for month_key in sorted(monthly.keys()):
        monthly_data.append(
            {
                "month": month_key,
                "days": _calc_days(monthly[month_key], hours_in_day),
            }
        )
    usage["monthly_data"] = monthly_data

    # Running cumulative for burn-down
    cumulative = Decimal()
    for entry in monthly_data:
        cumulative += entry["days"]
        entry["cumulative"] = cumulative

    # Avg stats
    job_count = len(jobs_data)
    phase_count = sum(len(j["phases"]) for j in jobs_data)
    total_days = usage["roles_total"]
    usage["avg_days_per_job"] = round(total_days / job_count, 1) if job_count else 0
    usage["avg_days_per_phase"] = (
        round(total_days / phase_count, 1) if phase_count else 0
    )
    usage["job_count"] = job_count
    usage["phase_count"] = phase_count
    return usage
